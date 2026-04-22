# Product Plan

## Phase 2: Goals and Non-Goals
### Goals
- Develop a functional MVP for scraping data.
- Establish a reliable data fetching mechanism.
### Non-Goals
- Implement complex user interfaces.
- Support multiple formats initially.

## Phased Milestones
### Phase 2: Scraper MVP
- [ ] Create initial scraping logic.
- [ ] Test data fetching reliability.

### Phase 3: Notifications
- [ ] Implement notification functionality based on scraped data.
- [ ] Set up user preferences for notifications.

### Phase 4: Web UI
- [ ] Design user interface for the web application.
- [ ] Develop frontend components for data display.

### Phase 5: NixOS Integration on wh-server
- [ ] Configure NixOS for deployment.
- [ ] Test deployment process on wh-server.

### Phase 6: Hardening/Ops
- [ ] Establish security measures for the application.
- [ ] Define operational procedures for monitoring and maintenance.

## Architecture Overview
- Describe system architecture including major components and their interactions.

## Configuration and Secrets
- `DATABASE_URL`: Your database connection string.
- `SKOLEINTRA_*` env vars: Environment variables for the application.
- `agenix` on wh-server: Configuration management tool setup.

## Data Model Summary
- **Children**: Represents users/participants.
- **Items**: Represents data structures being scraped.
- **Attachments**: Files associated with items.
- **Notification Settings**: User preferences for notifications.

## Implementation Tasks Per Phase
- **Phase 2: Scraper MVP**
  - [ ] Develop scraping logic.
  - [ ] Write unit tests.

- **Phase 3: Notifications**
  - [ ] Implement notification system.
  - [ ] Test notifications.

…

## Testing Strategy
- Unit tests for each component.
- Integration testing for system interaction.
- User acceptance testing (UAT) for end-user feedback.

## Rollout Plan
- Phased rollout starting with a limited user base.
- Gather feedback and iterate before major release.

## Open Questions/Risks
- **UNI-login JS changes**: How will updates affect the current implementation?
- **Captcha**: Are there potential issues with implementing captchas for the scraper?
- **Rate limiting**: What are the limits imposed by data sources?
- **HTML changes**: How resilient is the scraper to changes in HTML structure?