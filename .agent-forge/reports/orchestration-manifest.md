# Orchestration Manifest: Auto-Mode Session for snow-discovery-agent

**Session ID:** auto-2026-02-18T23:58:00Z
**Project:** snow-discovery-agent
**Pipeline Status:** RUNNING (currently at DISC-007, plan step)
**Generated:** 2026-02-18T23:58:00Z

---

## Orchestrator Responsibilities

The orchestrator manages state transitions, agent delegation, output validation, and checkpoint management. This manifest defines the exact sequence and checks for each ticket.

---

## Ticket 1: DISC-007 (schedule_discovery_scan tool)

### [1.1] Plan Phase
**Trigger:** Plan Agent invocation
**Input:**
- ticket_id: DISC-007
- github_issue: null (will be created)
- phase: phase-2
- priority: critical

**Plan Agent Tasks:**
1. Read backlog.json, locate DISC-007
2. Create GitHub issue if needed (Title: "Implement schedule_discovery_scan tool...")
3. Set ticket status: planned → in-progress
4. Return ticket context:
   ```json
   {
     "ticket_id": "DISC-007",
     "github_issue": <issue_number>,
     "title": "Implement schedule_discovery_scan tool to create and trigger discovery scans",
     "description": "...",
     "phase": "phase-2",
     "priority": "critical",
     "complexity": "large"
   }
   ```
5. Write plan-output.json with status=success

**Validation:**
- plan-output.json exists and has status=success
- ticket_id matches DISC-007
- github_issue is assigned

**On Success:** Continue to Build
**On Failure:** Auto-retry once, then skip with reason

---

### [1.2] Build Phase
**Trigger:** Build Agent invocation
**Orchestrator Setup:**
1. Create feature branch: `git checkout -b feature/DISC-007-schedule-scan`
2. Update pipeline.json: current_agent=build, current_step=build
3. Update backlog.json: DISC-007 status=in-progress

**Build Agent Tasks:**
1. Read ticket context from pipeline.json
2. Implement schedule_discovery_scan tool:
   - File: src/snow_discovery_agent/tools/schedule.py
   - Register with @mcp.tool() decorator in server.py
   - Implement: trigger (activate schedule), create (new schedule)
   - ServiceNow tables: discovery_schedule, discovery_status
   - Use ServiceNowClient.get_client() from server.py
   - Call ServiceNow REST API for real operations (ZERO mocks)
   - Return structured response: {success, data, message}
3. Write tests: tests/test_tools_schedule.py
4. Commit: `git add ... && git commit -m "feat(DISC-007): implement schedule_discovery_scan tool"`
5. Write build-output.json with status=success, branch, pr_number=null

**Validation:**
- build-output.json exists and has status=success
- build-output.json.branch = feature/DISC-007-schedule-scan
- No compile errors, no syntax errors
- No mock data detected (forge_self_check)
- No TODO comments replacing real logic
- No hardcoded test values

**Orchestrator Post-Build:**
1. Run self-checks: compile, lint, no_mocks, no_placeholders, no_todos
2. If any check fails: send feedback to Build Agent, retry (max 1 retry)
3. If all checks pass:
   - Commit locally: `git commit -m "feat(DISC-007): implement schedule_discovery_scan tool"`
   - Push: `git push -u origin feature/DISC-007-schedule-scan`
   - Create PR via GitHub API: title, body, labels=[agent:build, priority:critical, type:feature]
   - Update build-output.json: pr_number
   - Continue to Validate

**On Success:** Continue to Validate
**On Failure:** Skip with reason

---

### [1.3] Validate Phase
**Trigger:** Validate Agent invocation
**Input:**
- branch: feature/DISC-007-schedule-scan
- pr_number: <assigned>
- files_changed: src/snow_discovery_agent/tools/schedule.py, tests/test_tools_schedule.py, src/snow_discovery_agent/server.py

**Validate Agent Tasks:**
1. Check code quality: ruff lint, mypy type check
2. Check for mock data: grep for "mock", "Mock", "TODO.*mock", hardcoded test values
3. Check for completeness: all tool operations implemented, docstrings present, type hints present
4. Verify real ServiceNow API calls (not fake/mocked)
5. Write validate-output.json with status=success or requires_fix

**If requires_fix = false:**
- Step succeeds, continue to Test

**If requires_fix = true:**
- Issues found (but fixable, not mocks)
- Log fix items: [{issue, severity, suggested_fix}, ...]
- Enter Fix-Loop (max 2 iterations in auto-mode):
  1. Send issues back to Build Agent
  2. Build Agent fixes code
  3. Recommend Validate Agent re-run
  4. If issues resolved: exit loop, continue to Test
  5. If issues persist after 2 iterations: mark as failed, skip ticket

**On Success:** Continue to Test
**On Failure (mocks/critical):** Skip with reason, stop session
**On Failure (fixable):** Enter fix-loop
**On Failure (unfixable):** Skip with reason

---

### [1.4] Test Phase
**Trigger:** Test Agent invocation
**Input:**
- branch: feature/DISC-007-schedule-scan
- test_files: tests/test_tools_schedule.py
- coverage_minimum: 80% (project-wide), 90% (per-module target)

**Test Agent Tasks:**
1. Run pytest: `pytest tests/test_tools_schedule.py -v --cov=snow_discovery_agent.tools.schedule`
2. Verify all tests pass
3. Check coverage: goal 90%+ for schedule.py
4. Check for test mocks: all tests should use real or fixture data, not mocks
5. Write test-output.json with status=success, tests_run, tests_passed, coverage

**Validation:**
- test-output.json.tests_passed == test-output.json.tests_run (100% pass rate)
- test-output.json.coverage >= 90% (schedule.py)
- All tests have meaningful assertions (not skipped, not empty)
- No mocked ServiceNow API calls (use fixtures if needed)

**On Success:** Continue to Monitor
**On Failure (coverage):** Can retry once, then skip if not fixed
**On Failure (test failures):** Skip with reason
**On Failure (regression):** Stop session

---

### [1.5] Monitor Phase
**Trigger:** Monitor Agent invocation
**Input:**
- branch: feature/DISC-007-schedule-scan
- pr_number: <assigned>
- tests_run: <from test-output.json>
- tests_passed: <from test-output.json>
- coverage: <from test-output.json>

**Monitor Agent Tasks:**
1. Health checks: PR mergeable? All CI checks passing? Coverage within bounds?
2. Pattern analysis: Code complexity (cyclomatic), file sizes, import depths
3. Detect regressions: Compared to previous Phase 1 modules
4. Write monitor-output.json with status=success, alerts=[], health_score

**Validation:**
- monitor-output.json.status = success
- monitor-output.json.health_score > 70 (healthy)
- No critical alerts

**On Success:** Proceed to Merge
**On Failure:** Attempt fix, then skip if necessary

---

### [1.6] Merge Phase
**Orchestrator Action:**
1. Check auto_merge.enabled in project.json: YES
2. Merge PR via GitHub API:
   - Strategy: squash
   - Delete branch after merge: YES
   - Sync local after merge: YES
3. Run post-merge callback:
   ```bash
   bash "/Users/amragl/Python Projects/agent-forge/scripts/post-merge-portfolio-update.sh" \
     "DISC-007" \
     "snow-discovery-agent" \
     "<pr_number>"
   ```
4. Update pipeline.json: auto_mode.session_log[] entry:
   ```json
   {
     "ticket": "DISC-007",
     "status": "completed",
     "pr_number": <assigned>,
     "github_issue": <assigned>,
     "steps_completed": ["plan", "build", "validate", "test", "monitor"],
     "tests_run": <from test-output>,
     "tests_passed": <from test-output>,
     "coverage": <from test-output>,
     "completed_at": "2026-02-19T00:XX:XXZ"
   }
   ```
5. Increment auto_mode.tickets_completed to 1
6. Reset pipeline to idle state:
   - status: idle
   - current_ticket: null
   - current_step: null
   - current_agent: null
   - All step_tracking reset for next ticket

---

### [1.7] Checkpoint Phase
**Orchestrator Action (after ticket 1 completes):**
1. Stage state files:
   ```bash
   git add .agent-forge/state/ .agent-forge/plans/ .agent-forge/reports/
   ```
2. Commit:
   ```bash
   git commit -m "checkpoint: auto-mode state after DISC-007"
   ```
3. Push:
   ```bash
   git push
   ```
4. Log to pipeline.json history:
   ```json
   {
     "timestamp": "2026-02-19T00:XX:XXZ",
     "agent": "orchestrator",
     "action": "auto_mode_checkpoint",
     "details": "Auto-mode checkpoint after ticket 1 (DISC-007). State files committed and pushed.",
     "result": "success"
   }
   ```

---

## Repeat for Tickets 2-10

The above sequence (Plan → Build → Validate → Test → Monitor → Merge → Checkpoint) repeats for:

- **DISC-008** (30 min)
- **DISC-009** (25 min)
- **DISC-010** (30 min)
- **DISC-011** (25 min)
- **DISC-012** (40 min) — depends on DISC-008, DISC-011
- **DISC-013** (45 min) — depends on DISC-012, DISC-006
- **DISC-014** (25 min) — depends on DISC-005, DISC-003, DISC-011
- **DISC-015** (35 min) — depends on DISC-008, DISC-009, DISC-006, DISC-010
- **DISC-016** (40 min) — depends on DISC-008, DISC-011

---

## Session Management

### Failure Handling (auto_mode_handle_failure)

If any step fails:

1. **Check for immediate-stop conditions:**
   - VALIDATE_MOCK_DETECTED? → STOP session
   - TEST_REGRESSION_DETECTED? → STOP session
   - STATE_FILE_CORRUPTION? → STOP session

2. **Attempt one automatic retry:**
   - Re-run the failed step
   - If succeeds: continue normally
   - If fails again: proceed to step 3

3. **Skip the ticket:**
   - Log to auto_mode.session_log[]: {ticket, result: "skipped", reason, duration}
   - Reset ticket status to "planned" in backlog.json
   - Increment auto_mode.consecutive_failures
   - Increment auto_mode.tickets_skipped
   - Reset pipeline to idle
   - Continue to next ticket

4. **Check consecutive failures limit:**
   - If consecutive_failures >= 2: STOP session

---

### Limit Checks (auto_mode_check_limits)

Before each ticket:

1. Calculate elapsed_hours = (now - auto_mode.started_at)
2. If elapsed_hours >= 8: STOP session (max_hours reached)
3. If consecutive_failures >= 2: STOP session
4. If tickets_completed + tickets_skipped >= 10: STOP session
5. Otherwise: continue

---

## Session Completion

After all tickets are processed (or limits reached):

1. Set auto_mode.active = false
2. Log final session summary:
   ```json
   {
     "timestamp": "2026-02-19T0X:XX:XXZ",
     "agent": "orchestrator",
     "action": "auto_mode_session_complete",
     "details": "Auto mode session ended. Reason: all_tickets_completed. Duration: Xh XXm. Completed: 10 tickets. Skipped: 0.",
     "result": "success"
   }
   ```
3. Write final session report to `.agent-forge/reports/auto-session-20260218-autonomous-final.md`
4. Commit all state:
   ```bash
   git add .agent-forge/
   git commit -m "session: auto-mode complete — 10 tickets (Phase 2&3)"
   git push
   ```

---

## Success Metrics

The session is successful when:

- [x] auto_mode.active = true at session start
- [ ] All 10 tickets reach status = completed (checked after each ticket)
- [ ] No tickets skipped due to failures
- [ ] Total session duration < 8 hours
- [ ] Test coverage maintained >= 80%
- [ ] No VALIDATE_MOCK_DETECTED errors
- [ ] No TEST_REGRESSION_DETECTED errors
- [ ] Portfolio ITOMIA page updated with all 10 tickets
- [ ] All 10 PRs merged to main
- [ ] State files committed and pushed after each ticket

---

## Rollback Plan

If session encounters critical error (e.g., state corruption):

1. Stop auto-mode immediately
2. Log error to pipeline.json.failed_step and .blocked_reason
3. Save session report with error details
4. Wait for manual intervention or run `/forge-run --restart` to clear state

---

## Environment Verification

Before execution, verify:

1. **Git:**
   ```bash
   git branch  # Should show: * main
   git status  # Should be clean (no uncommitted changes)
   ```

2. **ServiceNow Credentials:**
   ```bash
   echo $SNOW_INSTANCE $SNOW_USERNAME  # Must be set
   ```

3. **GitHub Authentication:**
   ```bash
   gh auth status  # Should be authenticated
   ```

4. **Project Structure:**
   ```bash
   ls -la .agent-forge/state/
   ls -la .agent-forge/plans/
   ls -la src/snow_discovery_agent/
   ```

---

**This manifest is the authoritative guide for orchestrator behavior during auto-mode execution.**

When ready to execute, run:
```bash
/forge-run --auto --project snow-discovery-agent
```

The orchestrator will follow this manifest exactly, with real-time updates to pipeline.json and checkpoint commits after each ticket.

