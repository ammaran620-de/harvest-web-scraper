# Development workflow

1. **Define an observable change.** Describe the expected records, endpoint response or failure behaviour.
2. **Create or update a fixture.** Use permitted public practice-source content; keep tests deterministic and remove unrelated data.
3. **Write a focused regression test.** Cover the behaviour that would fail before the change.
4. **Implement the smallest change.** Keep extraction in `scraper.py`, HTTP/storage concerns in `api.py`, and presentation in the frontend.
5. **Run the test suite.** Use `python -m unittest discover -s tests -v` inside the configured virtual environment.
6. **Smoke-test the feature.** Inspect `/docs`, run a small live scrape when appropriate, and check source provenance and error behaviour.
7. **Open a reviewable commit or pull request.** Explain the changed behaviour, relevant validation and remaining limitations. Let GitHub Actions run.
8. **Update verification evidence.** Record actual outcomes. Never copy a historical successful result into a claim about a new untested change.

Suggested commit descriptions describe behaviour, for example `Handle malformed prices without discarding valid products`. Keep the real history; do not manufacture past dates, fake pull requests or test badges.

Keep `.venv`, `data`, caches and credentials out of Git. The current project requires no API key. If optional model integration is added, put secrets in backend environment variables and keep browser code and exports free of them.
