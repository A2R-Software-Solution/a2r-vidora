# Configuration

Backend application settings are read centrally by `functions/app/core/config.py`.
Every settings field accepts its uppercase environment variable; process environment
overrides `functions/.env`. The file path is independent of the working directory.
See `functions/.env.example` for names and defaults. Restart the backend after changes;
Firebase resource settings and schedules require redeployment.

Frontend public build settings are read only by `frontend/src/config.js`.
Use `frontend/.env.example` and rebuild/redeploy after changing `VITE_*` variables.
Never place passwords, API secrets, cookies or database credentials in `VITE_*`.
Browser question limits are UX controls; backend limits remain authoritative.

Defaults are centralized in config for compatibility with existing deployments.
Application modules import config instead of embedding operational defaults.
Protocol strings, routes, SQL, security rules, prompts, UI copy/styles, test fixtures,
and historical database migrations remain code. Vector dimension 384 is a database
contract: changing it requires a migration and re-embedding existing data, not an
environment override. Any replacement embedding model must honor that contract.

Preserve the overall deadline ordering: provider work fits within the analysis
deadline, which is below the function deadline; browser analysis timeout should be
longer than the function deadline. Keep frontend display limits consistent with
the corresponding backend limits when configuring them.
