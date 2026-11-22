# Job Search deep links

`GET /job-link?source=linkedin|naukri&role=<role>&location=<optional>` returns a URL for the selected site. Role abbreviations such as `se`, `da`, and `devops` are expanded by the backend.

The React `JobSearch` component calls that endpoint and opens the returned URL in a new tab. Pass `role` and optional `location`, or pass `roles={["SE", "Data Analyst"]}` to render multiple pairs of buttons.

This feature only redirects to LinkedIn or Naukri search pages. It does not log in, scrape pages, call paid APIs, fetch listings, or guarantee the target site's result format.
