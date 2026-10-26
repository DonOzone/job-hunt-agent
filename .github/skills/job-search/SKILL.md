---
name: job-search
description: Find and rank jobs for the user from configured sites. Use when asked to search for jobs, refresh job listings, or order jobs by region, remote, relocation or salary package.
---

# Job search & ranking

1. Ensure `config/profile.yaml` and `config/sites.yaml` exist (`jobhunt init` creates them). Ask the user for target
   roles, regions (in priority order), remote preference, relocation openness and minimum package if missing,
   and write them into `profile.yaml` under `requirement`, `preferred_regions`, `prefer_remote`, `open_to_relocation`.
2. Add sites to `config/sites.yaml`. Prefer official public APIs (`greenhouse`, `lever`, `ashby`, `remoteok`,
   `arbeitnow`). Use `type: browser` with CSS selectors only for career pages that have no API.
   Never scrape LinkedIn/Indeed/Glassdoor — their terms forbid it.
3. Run `jobhunt search --top 20` (or `jobhunt run` for the full daily pipeline).
4. Re-order on request: `jobhunt rank --order salary,remote,region,relocation,match`.
5. Summarise `workspace/ranked-jobs.md` for the user: top 5 per region, highlight remote + relocation + best packages.


Jobs the user found elsewhere: use the `add-job` skill (`jobhunt add <url>`). Skipped jobs (memory) are hidden
from results; `jobhunt list --all` shows them.
