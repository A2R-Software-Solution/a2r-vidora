import SiteLink from "../components/common/SiteLink";
import { config } from "../config";
import { siteDetails } from "./siteDetails";

const emailLink = <a href={`mailto:${siteDetails.supportEmail}`}>{siteDetails.supportEmail}</a>;
const contactLink = <SiteLink href="/contact">contact our team</SiteLink>;

export const publicPages = {
  "/about": {
    label: "About",
    eyebrow: "Meet Vidora AI",
    title: "Less searching. More understanding.",
    description: "A closer look at Vidora AI, a video learning tool from A2R Software Solutions.",
    intro: "A useful idea can be buried halfway through a long video. Vidora AI helps you find it, understand it, and return to the moment it was explained.",
    sections: [
      { id: "what-we-do", title: "Your video, easier to explore", content: <>
        <p>Vidora AI turns the spoken content of a supported YouTube video into a searchable conversation. Ask a specific question and use timestamp links to check the answer against the original video.</p>
        <p>It is useful for revisiting a lecture, reviewing a talk, or finding a point in an interview. The goal is to help you navigate the source, with the video still there when you need more context.</p>
      </> },
      { id: "built-by", title: "Built by A2R Software Solutions", content: <>
        <p>Vidora AI is a product of {siteDetails.company}. We develop and maintain the service, and welcome feedback on what works and what could be clearer.</p>
        <p>Learn more at <a href={siteDetails.companyUrl} target="_blank" rel="noopener noreferrer">a2rsoftwaresolution.com (opens in a new tab)</a>, or {contactLink} about Vidora AI.</p>
      </> },
      { id: "what-to-expect", title: "A tool to help you check the source", content: <>
        <p>AI can mishear a word, miss context, or produce an incorrect answer. Treat a summary as a starting point and verify important information in the video. Vidora focuses on spoken content; it may miss details that appear only on screen.</p>
        <p>The current beta supports YouTube analysis. Other video sources and automatic Shorts creation are not available yet. Vidora AI is independently operated and is not affiliated with or endorsed by YouTube or Google.</p>
      </> },
    ],
  },
  "/how-it-works": {
    label: "How it works",
    eyebrow: "A quick guide",
    title: "From a video link to a useful answer.",
    description: "Learn how to analyze a YouTube video, follow its progress, and ask questions with Vidora AI.",
    intro: "Start with a video you have permission to process. Vidora prepares its spoken content so you can explore it through summaries and questions.",
    sections: [
      { id: "add-a-video", title: "01 / Add your YouTube link", content: <>
        <p>Paste a YouTube URL into the home-page form and select Analyze Video. Guests can submit videos up to 35 minutes; signed-in users can submit videos up to 3 hours. Processing may wait when transcription capacity is busy.</p>
        <p>Only submit content you own or have permission to process. Private, unavailable, live, or upcoming videos may not be supported.</p>
      </> },
      { id: "follow-progress", title: "02 / Follow the processing", content: <>
        <p>Vidora prepares the audio, transcribes its speech, and builds the summary and searchable passages. The workspace shows the processing stage while this happens. Submitting a video does not mean the analysis is already complete.</p>
        <p>The time needed depends on the video and service availability. If YouTube temporarily blocks access, processing may fail; try again later or report the issue from the Contact page.</p>
      </> },
      { id: "ask-and-check", title: "03 / Ask, then check the moment", content: <>
        <p>When the analysis finishes, questions become available. Ask about one idea at a time, such as “What reasons does the speaker give for changing the plan?” Use any timestamp returned with the answer to revisit that part of the video.</p>
        <p>Clear speech helps. Music, overlapping speakers, and specialist vocabulary can reduce transcription accuracy. Verify quotes and important conclusions against the source rather than relying on the answer alone.</p>
      </> },
      { id: "return-later", title: "Returning to an analysis", content: <>
        <p>Resume previous analysis can reopen a saved analysis from the same browser while it remains available. Results expire and are periodically cleared, so the workspace is not permanent storage.</p>
        <p>For access problems, {contactLink} with the video link, approximate time, and the error you saw. Never send your password or session cookies.</p>
      </> },
    ],
  },
  "/privacy": {
    label: "Privacy Policy",
    eyebrow: "Privacy Policy",
    title: "Privacy, explained plainly.",
    description: "How Vidora AI handles account information, video analyses, cookies, and third-party services.",
    intro: `This policy describes how ${siteDetails.company} handles information when you use Vidora AI. It covers both guest use and signed-in accounts.`,
    updated: true,
    sections: [
      { id: "information", title: "Information involved in using Vidora", content: <>
        <ul>
          <li><strong>Account information:</strong> your email address and Firebase account identifier, along with account creation information. Google or email/password sign-in is handled by Firebase Authentication.</li>
          <li><strong>Video and analysis information:</strong> the submitted YouTube URL, video title and duration when available, temporary audio, transcripts, timestamps, summaries, and processing status.</li>
          <li><strong>Questions and answers:</strong> questions you submit and the answers generated for your analysis.</li>
          <li><strong>Usage and technical information:</strong> requests, errors, browser or device information, IP addresses, and identifiers used by our hosting, analytics, and abuse-prevention services.</li>
          <li><strong>Support messages:</strong> information you choose to send by email or through the issue-report form.</li>
        </ul>
      </> },
      { id: "use-and-providers", title: "How information is used and shared", content: <>
        <p>We use this information to authenticate accounts, process videos, answer questions, restore analyses, operate the service, investigate problems, and limit abuse.</p>
        <p>Firebase and Google Cloud provide authentication and backend services, Vercel serves the website, and Supabase provides database storage. Groq receives audio for transcription and relevant transcript text and questions for AI summaries and answers. These providers process information needed to deliver their services.</p>
        <p>The site also uses Google Analytics, reCAPTCHA, YouTube embeds, and a Google AdSense script. An embedded player or third-party script may send browser, request, and device information to its provider when loaded or used. External sites and support forms have their own privacy practices.</p>
      </> },
      { id: "cookies", title: "Cookies, local storage, and advertising", content: <>
        <p>Authentication services use browser storage to maintain sign-in. Vidora stores the recent analysis identifier and submitted URL in local storage to support resuming or retrying an analysis. Signing out does not necessarily clear those saved browser records.</p>
        <p>Google and other third parties may place or read cookies, use web beacons, or collect IP addresses and other identifiers through analytics, security, embedded videos, and advertising services. AdSense code may contact Google even when no advertisement is visible.</p>
        <p>If ads are served, Google and third-party vendors may use cookies to personalize them based on previous visits to this site or other sites. You can manage personalized advertising through <a href="https://myadcenter.google.com/">Google My Ad Center</a> and find participating third-party opt-out options at <a href="https://optout.aboutads.info/">YourAdChoices</a>.</p>
        <p>See <a href="https://policies.google.com/technologies/partner-sites">how Google uses information from sites and apps</a> and <a href="https://policies.google.com/privacy">Google’s Privacy Policy</a>. This site uses reCAPTCHA, to which Google’s Privacy Policy and <a href="https://policies.google.com/terms">Terms of Service</a> apply.</p>
      </> },
      { id: "retention", title: "Storage and retention", content: <>
        <p>Audio is processed in temporary working storage. Analyses have an expiry time and scheduled cleanup removes expired video records and associated transcript and question-and-answer records. Availability and cleanup timing depend on the service configuration; this is not a permanent archive.</p>
        <p>Account records are managed separately from expiring analyses. Operational logs, support correspondence, and provider-managed records may follow different retention periods. Video expiry does not mean every associated record or provider copy is erased immediately.</p>
        <p>Guest analyses can be accessed by someone who has their analysis identifier. Avoid submitting sensitive information and keep analysis identifiers private. Third-party services may process information in countries other than your own.</p>
      </> },
      { id: "choices", title: "Your choices and requests", content: <>
        <p>You can use the guest flow within its limits, sign out of your account, or clear cookies and site data in your browser. Clearing browser data can remove your saved session and the ability to resume an analysis; it does not itself delete server records.</p>
        <p>For questions about your information, or to request access, correction, or deletion, email {emailLink}. Tell us which account or analysis your request concerns. We may need to verify ownership before acting. Available rights depend on the law that applies to you.</p>
      </> },
      { id: "updates", title: "Policy updates and contact", content: <>
        <p>We may update this page as the service changes. The date above identifies the latest revision. Privacy questions can be sent to {siteDetails.company} at {emailLink}.</p>
      </> },
    ],
  },
  "/terms": {
    label: "Terms of Use",
    eyebrow: "Terms of Use",
    title: "A few clear ground rules.",
    description: "Terms for using Vidora AI, including permitted content, AI limitations, accounts, and service availability.",
    intro: `These terms cover your use of Vidora AI, a product of ${siteDetails.company}. Please read them alongside our Privacy Policy.`,
    updated: true,
    sections: [
      { id: "service", title: "The service", content: <>
        <p>Vidora AI helps you explore supported YouTube videos through transcripts, summaries, and questions with timestamp references. By using the service, you agree to these terms. If you do not agree, please do not use it.</p>
        <p>The service is currently offered as a beta. Features, processing limits, and availability can change. References to planned features do not mean those features are available.</p>
      </> },
      { id: "your-content", title: "Content you submit", content: <>
        <p>Submit only content you own or have permission to process, and comply with applicable laws and the source platform’s terms. A publicly accessible link does not by itself give you copyright permission.</p>
        <p>You retain any rights you hold in submitted content. By submitting it, you authorize the processing and storage needed to provide the requested analysis through Vidora and its service providers. Using Vidora does not transfer ownership of a video or its creator’s work to you.</p>
      </> },
      { id: "accounts", title: "Accounts and acceptable use", content: <>
        <p>Keep your login details secure and provide accurate account information. Do not attempt to access another user’s account or data, bypass usage limits or access controls, disrupt the service, or submit unlawful content.</p>
        <p>We may restrict access to protect the service and its users when misuse or technical problems occur.</p>
      </> },
      { id: "ai-limitations", title: "AI output needs checking", content: <>
        <p>Transcriptions, summaries, timestamps, and answers can be incomplete or incorrect. Check important information and quotations against the original video. Output is informational and is not a substitute for qualified medical, legal, financial, or other professional advice.</p>
        <p>You are responsible for how you use or share generated output, including respecting the rights of the original content owner.</p>
      </> },
      { id: "availability", title: "Availability and saved results", content: <>
        <p>Video access depends on YouTube and other providers, so processing can fail or be delayed. We do not guarantee uninterrupted service, a particular processing time, or the accuracy of an answer.</p>
        <p>Analyses expire and are periodically removed. Do not rely on Vidora as your only copy of information you need. Our <SiteLink href="/privacy">Privacy Policy</SiteLink> explains the information involved in providing the service.</p>
      </> },
      { id: "changes-and-contact", title: "Changes, concerns, and contact", content: <>
        <p>We may revise these terms as Vidora develops and will update the date on this page. Nothing in these terms removes rights that applicable law does not allow to be waived.</p>
        <p>For questions or concerns, email {emailLink}. For a content-rights complaint, identify the source video, explain the concern, and include contact details so we can follow up.</p>
      </> },
    ],
  },
  "/contact": {
    label: "Contact",
    eyebrow: "We’re listening",
    title: "Talk to the team behind Vidora.",
    description: "Contact A2R Software Solutions for Vidora AI support, privacy requests, feedback, or content concerns.",
    intro: "A question, a rough edge, or an idea that could make Vidora more useful? Here is how to reach us.",
    sections: [
      { id: "email", title: "Email the team", content: <>
        <p>For product support, feedback, privacy requests, or content concerns, write to {siteDetails.company}.</p>
        <p className="public-contact-email">{emailLink}</p>
        <p>Company website: <a href={siteDetails.companyUrl} target="_blank" rel="noopener noreferrer">a2rsoftwaresolution.com (opens in a new tab)</a>.</p>
      </> },
      { id: "report-an-issue", title: "Something didn’t work?", content: <>
        <p>Share the YouTube link, the approximate time of the problem, your browser, and any error message. A screenshot can help, but remove personal or sensitive information first.</p>
        <p><a className="public-action" href={config.bugReportUrl} target="_blank" rel="noopener noreferrer">Open the issue-report form <span aria-hidden="true">↗</span><span className="sr-only"> (opens in a new tab)</span></a></p>
        <p>Never send passwords, sign-in codes, API keys, or browser session cookies.</p>
      </> },
      { id: "privacy-and-rights", title: "Privacy and content requests", content: <>
        <p>For an account or data request, email us with enough information to identify the account or analysis. For a content-rights concern, include the source video link and a description of the issue.</p>
        <p>You can read how information is handled in our <SiteLink href="/privacy">Privacy Policy</SiteLink> and review the <SiteLink href="/terms">Terms of Use</SiteLink> before sending a request.</p>
      </> },
    ],
  },
};
