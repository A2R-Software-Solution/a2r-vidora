"""Credit accounting rules. Pure tests always run; database tests need a
disposable PostgreSQL at TEST_DATABASE_URL migrated to head."""
import asyncio
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.config import settings
import unittest.mock

from app.services.credit_service import (
    CreditOwner, InsufficientCreditsError, daily_question_limit, ist_today, refund_on_failure,
    roll_daily, short_reservation_key, split_charge, video_credit_cost,
)


class CreditRuleTests(unittest.TestCase):
    def test_every_started_minute_costs_a_credit(self):
        self.assertEqual(video_credit_cost(1), 1)
        self.assertEqual(video_credit_cost(60), 1)
        self.assertEqual(video_credit_cost(61), 2)
        self.assertEqual(video_credit_cost(3 * 3600), 180)
        with self.assertRaises(ValueError):
            video_credit_cost(0)

    def test_free_allowance_is_spent_before_purchased_credits(self):
        self.assertEqual(split_charge(80, 300, 30), (30, 0))
        self.assertEqual(split_charge(20, 300, 30), (20, 10))
        self.assertEqual(split_charge(0, 300, 30), (0, 30))
        self.assertEqual(split_charge(30, 0, 30), (30, 0))

    def test_insufficient_credits_charge_nothing(self):
        with self.assertRaises(InsufficientCreditsError) as caught:
            split_charge(20, 20, 60)
        self.assertEqual((caught.exception.needed, caught.exception.available), (60, 40))

    def test_day_changes_at_ist_midnight(self):
        before = datetime(2026, 10, 17, 18, 29, tzinfo=timezone.utc)  # 23:59 IST
        after = before + timedelta(minutes=1)                          # 00:00 IST
        self.assertEqual(ist_today(before).day, 17)
        self.assertEqual(ist_today(after).day, 18)

    def test_daily_counters_reset_only_on_a_new_day(self):
        today = ist_today()
        account = SimpleNamespace(daily_date=today, daily_free_used=40, daily_chat_used=7)
        roll_daily(account, today)
        self.assertEqual((account.daily_free_used, account.daily_chat_used), (40, 7))
        roll_daily(account, today + timedelta(days=1))
        self.assertEqual((account.daily_free_used, account.daily_chat_used), (0, 0))

    def test_question_limits_by_tier(self):
        guest, user = CreditOwner(guest_key="g" * 64), CreditOwner(user_id=uuid.uuid4())
        self.assertEqual(daily_question_limit(guest, 0), settings.guest_daily_questions)
        self.assertEqual(daily_question_limit(user, 0), settings.user_daily_questions)
        self.assertEqual(daily_question_limit(user, 1), settings.paid_daily_questions)

    def test_only_our_failures_are_refunded(self):
        self.assertTrue(refund_on_failure(None))
        self.assertTrue(refund_on_failure("youtube_session_unavailable"))
        self.assertTrue(refund_on_failure("RENDER_FAILED"))
        self.assertFalse(refund_on_failure("no_speech"))

    def test_owner_needs_exactly_one_identity(self):
        with self.assertRaises(ValueError):
            CreditOwner()
        with self.assertRaises(ValueError):
            CreditOwner(user_id=uuid.uuid4(), guest_key="g")
        with self.assertRaises(ValueError):
            CreditOwner(user_id=uuid.uuid4(), cap_key="c")

    def test_each_short_attempt_has_its_own_key(self):
        short_id = uuid.uuid4()
        self.assertNotEqual(short_reservation_key(short_id, uuid.uuid4()),
                            short_reservation_key(short_id, uuid.uuid4()))


class CreditApiTests(unittest.TestCase):
    """HTTP behaviour with the wallet mocked; no database or provider calls."""

    def setUp(self):
        from unittest.mock import AsyncMock, Mock, patch
        from fastapi.testclient import TestClient
        from app.controller import qa_log_controller
        from app.core.rate_limit import limiter
        from app.deps import get_current_user_id, get_db
        from app.main import app
        from app.routes import credit_routes
        from app.services.credit_service import CreditSummary
        limiter.reset()
        self.addCleanup(limiter.reset)

        async def no_user():
            return None

        async def no_db():
            yield Mock(rollback=AsyncMock())
        app.dependency_overrides[get_current_user_id] = no_user
        app.dependency_overrides[get_db] = no_db
        self.addCleanup(app.dependency_overrides.clear)
        self.credits = Mock(
            summary=AsyncMock(return_value=CreditSummary(free_left=30, free_daily=45, purchased_balance=0,
                                                         questions_left=10, is_paid=False)),
            consume_question=AsyncMock(), return_question=AsyncMock())
        self.qa = Mock(ask=AsyncMock())
        for target, value in ((credit_routes, self.credits), (qa_log_controller, self.credits)):
            patcher = patch.object(target, "CreditService", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(qa_log_controller, "QALogService", return_value=self.qa)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def ask(self):
        return self.client.post(f"/videos/{uuid.uuid4()}/qa/ask", json={"question": "Why?"})

    def test_balance_endpoint(self):
        body = self.client.get("/credits").json()
        self.assertEqual((body["available"], body["free_left"], body["short_credit_cost"]),
                         (30, 30, settings.short_credit_cost))

    def test_guests_share_a_wallet_per_ip_and_users_are_separate(self):
        from fastapi import Request
        from app.core.rate_limit import credit_owner_for
        def request(ip):
            return Request({"type": "http", "client": (ip, 1), "headers": []})
        with unittest.mock.patch.object(settings, "rate_limit_trusted_proxy_hops", 0):
            first, again, other = (credit_owner_for(request(ip), None) for ip in ("192.0.2.1", "192.0.2.1", "192.0.2.2"))
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertNotIn("192.0.2.1", first.guest_key)
        user = uuid.uuid4()
        self.assertEqual(credit_owner_for(request("192.0.2.1"), user).user_id, user)

    def test_guest_device_header_picks_wallet_and_ip_picks_shared_allowance(self):
        from fastapi import Request
        from app.core.rate_limit import credit_owner_for
        device_a, device_b = str(uuid.uuid4()), str(uuid.uuid4())

        def owner(ip, device=None):
            headers = [(b"x-guest-id", device.encode())] if device else []
            return credit_owner_for(Request({"type": "http", "client": (ip, 1), "headers": headers}), None)
        with unittest.mock.patch.object(settings, "rate_limit_trusted_proxy_hops", 0):
            same_wifi = owner("192.0.2.1", device_a), owner("192.0.2.1", device_b)
            travelling = owner("192.0.2.9", device_a)
            upper = owner("192.0.2.1", device_a.upper())
            bad_header = owner("192.0.2.1", "not-a-uuid")
            no_header = owner("192.0.2.1")
        self.assertNotEqual(same_wifi[0].guest_key, same_wifi[1].guest_key)
        self.assertEqual(same_wifi[0].cap_key, same_wifi[1].cap_key)
        self.assertEqual(travelling.guest_key, same_wifi[0].guest_key)
        self.assertNotEqual(travelling.cap_key, same_wifi[0].cap_key)
        self.assertEqual(upper, same_wifi[0])
        self.assertEqual(bad_header.guest_key, no_header.guest_key)
        self.assertNotEqual(no_header.guest_key, no_header.cap_key)
        self.assertNotIn(device_a, same_wifi[0].guest_key)

    def test_old_frontend_can_create_shorts_only_when_affordable(self):
        from unittest.mock import AsyncMock, patch
        from app.routes import short_routes
        from app.services.credit_service import CreditSummary
        jobs = [SimpleNamespace(id=uuid.uuid4(), video_id=uuid.uuid4(), start_time=0, end_time=30,
                                status="completed", error_code=None, created_at=datetime.now(timezone.utc),
                                expires_at=datetime.now(timezone.utc) + timedelta(hours=1))]
        for available, can_create in ((settings.short_credit_cost * 2 + 1, True),
                                      (settings.short_credit_cost - 1, False)):
            self.credits.summary.return_value = CreditSummary(
                free_left=available, free_daily=45, purchased_balance=0, questions_left=10, is_paid=False)
            with patch.object(short_routes, "CreditService", return_value=self.credits), \
                 patch.object(short_routes, "ShortService") as shorts:
                shorts.return_value.list = AsyncMock(return_value=jobs)
                body = self.client.get(f"/videos/{uuid.uuid4()}/shorts").json()
            # The current frontend enables creation while used < free_limit.
            self.assertEqual(body["used"] < body["free_limit"], can_create)

    def test_daily_question_limit_is_a_429_with_a_code(self):
        from app.services.credit_service import ChatLimitError
        self.credits.consume_question.side_effect = ChatLimitError(10)
        response = self.ask()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "daily_question_limit")
        self.qa.ask.assert_not_awaited()

    def test_unanswered_question_is_given_back(self):
        from app.integration.groq_client import GroqRequestError
        self.qa.ask.side_effect = GroqRequestError("down")
        self.assertEqual(self.ask().status_code, 503)
        self.credits.return_question.assert_awaited_once()

    def test_insufficient_credits_is_a_402_with_amounts(self):
        self.credits.summary.side_effect = InsufficientCreditsError(60, 40)
        response = self.client.get("/credits")
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.json(), {"detail": "Not enough credits for this request.",
                                           "code": "insufficient_credits", "needed": 60, "available": 40})


class VideoSubmitCreditTests(unittest.IsolatedAsyncioTestCase):
    async def test_reused_analysis_is_charged_in_the_same_commit(self):
        from unittest.mock import AsyncMock, Mock, patch
        from app.schemas.video_schema import VideoCreate
        from app.services import video_service as module
        source = SimpleNamespace(id=uuid.uuid4(), title="T", duration=125, summary="S",
                                 processing_total_chunks=1, processing_completed_chunks=1,
                                 expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        db = Mock(add=Mock(), add_all=Mock(), commit=AsyncMock(), refresh=AsyncMock())
        service = module.VideoService(db)
        service._repo = Mock(get_by_id=AsyncMock(return_value=None),
                             find_reusable_completed=AsyncMock(return_value=source))
        service._chunk_repo = Mock(list_by_video=AsyncMock(return_value=[]))
        hold = SimpleNamespace(id=uuid.uuid4())
        owner = CreditOwner(guest_key="g" * 64)
        for paid in (False, True):
            with self.subTest(paid=paid):
                credits = Mock(summary=AsyncMock(return_value=SimpleNamespace(is_paid=paid)),
                               reserve_video=AsyncMock(return_value=hold), settle=AsyncMock())
                request_id = uuid.uuid4()
                service._repo.get_by_id = AsyncMock(return_value=None)
                with patch.object(module, "CreditService", return_value=credits) as factory:
                    video, _ = await service.submit_once(VideoCreate(youtube_url="https://youtu.be/yYF2Vf1Gc14"),
                                                         user_id=None, request_id=request_id, owner=owner)
                self.assertFalse(factory.call_args.kwargs["commit"])
                credits.reserve_video.assert_awaited_once_with(owner, request_id, 3)
                credits.settle.assert_awaited_once_with(hold.id)
                self.assertEqual(video.guest_key, owner.guest_key)
                self.assertEqual(video.priority, paid)
                if paid:
                    # A paid copy owns its chunks, so it outlives the 1-hour source.
                    self.assertGreater(video.expires_at - datetime.now(timezone.utc),
                                       timedelta(hours=settings.paid_retention_hours - 1))
                else:
                    self.assertEqual(video.expires_at, source.expires_at)

    async def test_paid_submission_gets_priority_and_paid_retention(self):
        from unittest.mock import AsyncMock, Mock, patch
        from app.schemas.video_schema import VideoCreate
        from app.services import video_service as module
        for paid, hours in ((False, settings.video_retention_hours), (True, settings.paid_retention_hours)):
            with self.subTest(paid=paid):
                service = module.VideoService(Mock(commit=AsyncMock()))
                service._repo = Mock(get_by_id=AsyncMock(return_value=None), create_once=AsyncMock(),
                                     find_reusable_completed=AsyncMock(return_value=None))
                service.get_for_user = AsyncMock(side_effect=RuntimeError("stop after create"))
                credits = Mock(ensure_available=AsyncMock(return_value=SimpleNamespace(is_paid=paid)))
                with patch.object(module, "CreditService", return_value=credits):
                    with self.assertRaises(RuntimeError):
                        await service.submit_once(VideoCreate(youtube_url="https://youtu.be/yYF2Vf1Gc14"),
                                                  user_id=uuid.uuid4(), request_id=uuid.uuid4(),
                                                  owner=CreditOwner(user_id=uuid.uuid4()))
                values = service._repo.create_once.call_args.kwargs
                self.assertEqual(values["priority"], paid)
                lifetime = values["expires_at"] - datetime.now(timezone.utc)
                self.assertAlmostEqual(lifetime.total_seconds(), hours * 3600, delta=60)

    def test_paid_videos_shorts_share_paid_retention(self):
        from unittest.mock import AsyncMock, Mock, patch
        from app.schemas.short_schema import ShortRequest
        from app.services.short_service import ShortService
        import asyncio
        far = datetime.now(timezone.utc) + timedelta(days=30)
        for priority, hours in ((False, settings.shorts_retention_hours), (True, settings.paid_retention_hours)):
            db = Mock(add=Mock(), commit=AsyncMock(), refresh=AsyncMock(),
                      execute=AsyncMock(side_effect=[Mock(), Mock(scalars=Mock(return_value=[]))]))
            service = ShortService(db)
            service._video = AsyncMock(return_value=SimpleNamespace(duration=100, expires_at=far, priority=priority))
            with patch("app.services.short_service.VideoService"), \
                 patch("app.services.short_service.TranscriptChunkRepository") as chunks:
                chunks.return_value.find_in_time_range = AsyncMock(return_value=[SimpleNamespace(chunk_text="hi")])
                job, _ = asyncio.run(service.create(uuid.uuid4(), ShortRequest(start_time=0, end_time=30), None))
            lifetime = job.expires_at - datetime.now(timezone.utc)
            self.assertAlmostEqual(lifetime.total_seconds(), hours * 3600, delta=60)

    async def test_new_submission_needs_some_credit_and_records_the_guest(self):
        from unittest.mock import AsyncMock, Mock, patch
        from app.schemas.video_schema import VideoCreate
        from app.services import video_service as module
        service = module.VideoService(Mock(commit=AsyncMock()))
        service._repo = Mock(get_by_id=AsyncMock(return_value=None),
                             find_reusable_completed=AsyncMock(return_value=None), create_once=AsyncMock())
        owner = CreditOwner(guest_key="g" * 64)
        credits = Mock(ensure_available=AsyncMock(side_effect=InsufficientCreditsError(1, 0)))
        with patch.object(module, "CreditService", return_value=credits):
            with self.assertRaises(InsufficientCreditsError):
                await service.submit_once(VideoCreate(youtube_url="https://youtu.be/yYF2Vf1Gc14"),
                                          user_id=None, request_id=uuid.uuid4(), owner=owner)
        service._repo.create_once.assert_not_awaited()


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL is not set")
class CreditDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from app.models.user_model import User
        self.engine = create_async_engine(TEST_DATABASE_URL)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.sessions() as db:
            user = User(firebase_uid=str(uuid.uuid4()), email=f"{uuid.uuid4()}@test.local")
            db.add(user)
            await db.commit()
        self.owner = CreditOwner(user_id=user.id)

    async def asyncTearDown(self):
        await self.engine.dispose()

    def service(self, db):
        from app.services.credit_service import CreditService
        return CreditService(db)

    async def add_purchased(self, amount):
        from app.models.credit_model import CreditAccount
        from sqlalchemy import update
        async with self.sessions() as db:
            await self.service(db).summary(self.owner)
            await db.execute(update(CreditAccount).where(CreditAccount.user_id == self.owner.user_id)
                             .values(purchased_balance=amount))
            await db.commit()

    async def reserve(self, amount, key=None, source_type="video", source_id=None):
        async with self.sessions() as db:
            return await self.service(db).reserve(
                self.owner, source_type=source_type, source_id=source_id or uuid.uuid4(),
                idempotency_key=key or f"test:{uuid.uuid4()}", amount=amount)

    async def summary(self):
        async with self.sessions() as db:
            return await self.service(db).summary(self.owner)

    async def ledger(self, reservation_id):
        from sqlalchemy import select
        from app.models.credit_model import CreditLedgerEntry
        async with self.sessions() as db:
            rows = (await db.execute(select(CreditLedgerEntry.kind, CreditLedgerEntry.bucket,
                                            CreditLedgerEntry.amount).where(
                CreditLedgerEntry.reservation_id == reservation_id))).all()
        return sorted(tuple(row) for row in rows)

    async def test_reserve_then_settle_keeps_the_charge(self):
        await self.add_purchased(100)
        reservation = await self.reserve(settings.user_daily_credits + 10)
        async with self.sessions() as db:
            self.assertTrue(await self.service(db).settle(reservation.id))
            self.assertFalse(await self.service(db).settle(reservation.id))
        summary = await self.summary()
        self.assertEqual((summary.free_left, summary.purchased_balance), (0, 90))
        self.assertEqual(await self.ledger(reservation.id), sorted([
            ("reserve", "free", -settings.user_daily_credits), ("reserve", "purchased", -10)]))

    async def test_our_failure_returns_credits_to_their_buckets(self):
        await self.add_purchased(100)
        reservation = await self.reserve(settings.user_daily_credits + 10)
        async with self.sessions() as db:
            self.assertTrue(await self.service(db).finish_failed(reservation.id, reason="RENDER_FAILED"))
            # A second failure report (e.g. pipeline and cleanup racing) refunds nothing more.
            self.assertFalse(await self.service(db).finish_failed(reservation.id, reason="RENDER_FAILED"))
        summary = await self.summary()
        self.assertEqual((summary.free_left, summary.purchased_balance), (settings.user_daily_credits, 100))

    async def test_user_caused_failure_keeps_the_charge(self):
        reservation = await self.reserve(10)
        async with self.sessions() as db:
            self.assertFalse(await self.service(db).finish_failed(reservation.id, reason="no_speech"))
        self.assertEqual((await self.summary()).free_left, settings.user_daily_credits - 10)

    async def test_released_settle_and_settled_release_are_noops(self):
        reservation = await self.reserve(10)
        async with self.sessions() as db:
            await self.service(db).finish_failed(reservation.id, reason=None)
            self.assertFalse(await self.service(db).settle(reservation.id))
        self.assertEqual((await self.summary()).free_left, settings.user_daily_credits)

    async def test_duplicate_key_charges_once(self):
        from app.services.credit_service import ReservationClosedError
        first = await self.reserve(10, key="dup-key-" + str(uuid.uuid4()))
        again = await self.reserve(10, key=first.idempotency_key)
        self.assertEqual(first.id, again.id)
        self.assertEqual((await self.summary()).free_left, settings.user_daily_credits - 10)
        async with self.sessions() as db:
            await self.service(db).finish_failed(first.id, reason=None)
        with self.assertRaises(ReservationClosedError):
            await self.reserve(10, key=first.idempotency_key)

    async def test_insufficient_credits_reserve_nothing(self):
        await self.add_purchased(5)
        with self.assertRaises(InsufficientCreditsError):
            await self.reserve(settings.user_daily_credits + 6)
        summary = await self.summary()
        self.assertEqual((summary.free_left, summary.purchased_balance), (settings.user_daily_credits, 5))

    async def test_concurrent_reservations_never_overspend(self):
        await self.add_purchased(0)
        cost = settings.user_daily_credits // 2 + 1  # only one of two can fit
        results = await asyncio.gather(self.reserve(cost), self.reserve(cost), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, InsufficientCreditsError) for r in results), 1)
        self.assertEqual((await self.summary()).free_left, settings.user_daily_credits - cost)

    async def test_yesterdays_free_credits_are_not_refunded_into_today(self):
        from sqlalchemy import update
        from app.models.credit_model import CreditReservation
        reservation = await self.reserve(10)
        async with self.sessions() as db:
            await db.execute(update(CreditReservation).where(CreditReservation.id == reservation.id)
                             .values(created_at=datetime.now(timezone.utc) - timedelta(days=1)))
            await db.commit()
            # Simulate today's counter already being in use after the reset.
            await self.service(db).finish_failed(reservation.id, reason=None)
        self.assertEqual((await self.summary()).free_left, settings.user_daily_credits - 10)

    async def test_question_limit(self):
        from app.services.credit_service import ChatLimitError
        async with self.sessions() as db:
            service = self.service(db)
            for _ in range(settings.user_daily_questions):
                await service.consume_question(self.owner)
            with self.assertRaises(ChatLimitError):
                await service.consume_question(self.owner)
            await service.return_question(self.owner)
            await service.consume_question(self.owner)

    async def test_reconcile_waits_for_running_jobs_and_finishes_ended_ones(self):
        from sqlalchemy import update
        from app.models.credit_model import CreditReservation
        from app.models.video_model import Video, VideoStatus
        async with self.sessions() as db:
            videos = {}
            for status, stage in ((VideoStatus.PROCESSING, "waiting_for_quota"),
                                  (VideoStatus.COMPLETED, "completed"),
                                  (VideoStatus.FAILED, "youtube_session_unavailable")):
                video = Video(user_id=self.owner.user_id, youtube_id="x", youtube_url="https://youtu.be/x",
                              status=status, processing_stage=stage,
                              expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
                db.add(video)
                videos[status] = video
            await db.commit()
        held = {status: await self.reserve(10, source_id=video.id) for status, video in videos.items()}
        async with self.sessions() as db:
            await db.execute(update(CreditReservation).where(
                CreditReservation.id.in_([r.id for r in held.values()]))
                .values(created_at=datetime.now(timezone.utc) - timedelta(hours=2)))
            await db.commit()
            await self.service(db).reconcile_held(older_than=timedelta(hours=1))
            statuses = {status: (await db.get(CreditReservation, r.id, populate_existing=True)).status
                        for status, r in held.items()}
        self.assertEqual(statuses, {VideoStatus.PROCESSING: "held", VideoStatus.COMPLETED: "settled",
                                    VideoStatus.FAILED: "released"})

    async def test_superseded_short_attempt_is_refunded(self):
        from sqlalchemy import update
        from app.models.credit_model import CreditReservation
        from app.models.short_model import Short
        from app.models.video_model import Video, VideoStatus
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        async with self.sessions() as db:
            video = Video(user_id=self.owner.user_id, youtube_id="x", youtube_url="https://youtu.be/x",
                          status=VideoStatus.COMPLETED, expires_at=expires)
            db.add(video)
            await db.flush()
            short = Short(video_id=video.id, start_time=0, end_time=30, status="queued",
                          attempt_id=uuid.uuid4(), expires_at=expires)
            db.add(short)
            await db.commit()
        old = await self.reserve(settings.short_credit_cost, source_type="short", source_id=short.id,
                                 key=short_reservation_key(short.id, uuid.uuid4()))
        current = await self.reserve(settings.short_credit_cost, source_type="short", source_id=short.id,
                                     key=short_reservation_key(short.id, short.attempt_id))
        async with self.sessions() as db:
            await db.execute(update(CreditReservation).where(CreditReservation.id.in_([old.id, current.id]))
                             .values(created_at=datetime.now(timezone.utc) - timedelta(hours=2)))
            await db.commit()
            await self.service(db).reconcile_held(older_than=timedelta(hours=1))
            old_status = (await db.get(CreditReservation, old.id, populate_existing=True)).status
            current_status = (await db.get(CreditReservation, current.id, populate_existing=True)).status
        self.assertEqual((old_status, current_status), ("released", "held"))

    async def completed_video(self, **values):
        from app.models.video_model import Video, VideoStatus
        async with self.sessions() as db:
            video = Video(user_id=self.owner.user_id, youtube_id="x", youtube_url="https://youtu.be/x",
                          status=VideoStatus.COMPLETED, duration=100,
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=1), **values)
            db.add(video)
            await db.commit()
        return video

    async def test_video_redelivery_reuses_hold_and_retry_after_refund_charges_again(self):
        video_id = uuid.uuid4()
        async with self.sessions() as db:
            service = self.service(db)
            first = await service.reserve_video(self.owner, video_id, 10)
            self.assertEqual((await service.reserve_video(self.owner, video_id, 10)).id, first.id)
            self.assertEqual((await service.video_hold(video_id)).id, first.id)
            await service.finish_failed(first.id, reason=None)
            self.assertIsNone(await service.video_hold(video_id))
            retry = await service.reserve_video(self.owner, video_id, 10)
        self.assertNotEqual(retry.id, first.id)
        self.assertEqual((await self.summary()).free_left, settings.user_daily_credits - 10)

    async def test_dead_video_worker_is_refunded_but_quota_wait_is_not(self):
        from sqlalchemy import update
        from app.models.credit_model import CreditReservation
        from app.models.video_model import Video, VideoStatus
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        holds = {}
        for stage in ("chunk_transcription", "waiting_for_quota"):
            video = await self.completed_video()
            async with self.sessions() as db:
                await db.execute(update(Video).where(Video.id == video.id).values(
                    status=VideoStatus.PROCESSING, processing_stage=stage, processing_updated_at=old))
                await db.commit()
                holds[stage] = await self.service(db).reserve_video(self.owner, video.id, 10)
                await db.execute(update(CreditReservation).where(CreditReservation.id == holds[stage].id)
                                 .values(created_at=old))
                await db.commit()
        async with self.sessions() as db:
            await self.service(db).reconcile_held(older_than=timedelta(hours=1))
            statuses = {stage: (await db.get(CreditReservation, hold.id, populate_existing=True)).status
                        for stage, hold in holds.items()}
        self.assertEqual(statuses, {"chunk_transcription": "released", "waiting_for_quota": "held"})

    async def test_short_and_its_charge_commit_together(self):
        from unittest.mock import AsyncMock, patch
        from sqlalchemy import func, select
        from app.models.credit_model import CreditReservation
        from app.models.short_model import Short
        from app.schemas.short_schema import ShortRequest
        from app.services.short_service import ShortService
        video = await self.completed_video()
        await self.add_purchased(0)
        await self.reserve(settings.user_daily_credits - settings.short_credit_cost + 1)
        with patch("app.services.short_service.TranscriptChunkRepository") as chunks:
            chunks.return_value.find_in_time_range = AsyncMock(return_value=[SimpleNamespace(chunk_text="hi")])
            async with self.sessions() as db:
                with self.assertRaises(InsufficientCreditsError):
                    await ShortService(db).create(video.id, ShortRequest(start_time=0, end_time=30),
                                                  self.owner.user_id, self.owner)
            async with self.sessions() as db:
                self.assertEqual((await db.execute(select(func.count()).select_from(Short)
                                                   .where(Short.video_id == video.id))).scalar(), 0)
            await self.add_purchased(settings.short_credit_cost)
            async with self.sessions() as db:
                job, created = await ShortService(db).create(
                    video.id, ShortRequest(start_time=0, end_time=30), self.owner.user_id, self.owner)
            async with self.sessions() as db:
                hold = (await db.execute(select(CreditReservation).where(
                    CreditReservation.source_id == job.id))).scalar_one()
        self.assertTrue(created)
        self.assertEqual((hold.status, hold.free_amount + hold.purchased_amount),
                         ("held", settings.short_credit_cost))

    def guests_on_one_ip(self, count):
        cap = uuid.uuid4().hex
        return [CreditOwner(guest_key=uuid.uuid4().hex, cap_key=cap) for _ in range(count)]

    async def guest_reserve(self, owner, amount):
        async with self.sessions() as db:
            return await self.service(db).reserve(
                owner, source_type="video", source_id=uuid.uuid4(),
                idempotency_key=f"test:{uuid.uuid4()}", amount=amount)

    async def guest_summary(self, owner):
        async with self.sessions() as db:
            return await self.service(db).summary(owner)

    async def test_new_device_ids_on_one_ip_share_its_daily_allowance(self):
        per_device, per_ip = settings.guest_daily_credits, settings.guest_ip_daily_credits
        devices = self.guests_on_one_ip(per_ip // per_device + 1)
        holds = [await self.guest_reserve(device, per_device) for device in devices[:-1]]
        last = devices[-1]
        self.assertEqual((await self.guest_summary(last)).free_left, per_ip % per_device)
        with self.assertRaises(InsufficientCreditsError):
            await self.guest_reserve(last, per_device)
        # Refunding one device's failed job frees room on the shared allowance too.
        async with self.sessions() as db:
            await self.service(db).finish_failed(holds[0].id, reason=None)
        self.assertEqual((await self.guest_summary(last)).free_left, per_device)
        self.assertEqual((await self.guest_summary(devices[0])).free_left, per_device)

    async def test_another_ip_has_its_own_allowance(self):
        crowded = self.guests_on_one_ip(settings.guest_ip_daily_credits // settings.guest_daily_credits)
        for device in crowded:
            await self.guest_reserve(device, settings.guest_daily_credits)
        elsewhere = CreditOwner(guest_key=crowded[0].guest_key, cap_key=uuid.uuid4().hex)
        fresh = CreditOwner(guest_key=uuid.uuid4().hex, cap_key=elsewhere.cap_key)
        self.assertEqual((await self.guest_summary(fresh)).free_left, settings.guest_daily_credits)

    async def test_guest_questions_are_capped_per_ip(self):
        from app.services.credit_service import ChatLimitError
        devices = self.guests_on_one_ip(settings.guest_ip_daily_questions // settings.guest_daily_questions + 1)
        async with self.sessions() as db:
            service = self.service(db)
            for device in devices[:-1]:
                for _ in range(settings.guest_daily_questions):
                    await service.consume_question(device)
            with self.assertRaises(ChatLimitError):
                await service.consume_question(devices[-1])
            await service.return_question(devices[0])
            await service.consume_question(devices[-1])

    async def test_database_rejects_a_second_release_entry(self):
        from sqlalchemy.exc import IntegrityError
        from app.models.credit_model import CreditLedgerEntry
        reservation = await self.reserve(10)
        async with self.sessions() as db:
            await self.service(db).finish_failed(reservation.id, reason=None)
            db.add(CreditLedgerEntry(account_id=reservation.account_id, kind="release", bucket="free",
                                     amount=10, reservation_id=reservation.id, purchased_balance_after=0))
            with self.assertRaises(IntegrityError):
                await db.commit()


if __name__ == "__main__":
    unittest.main()
