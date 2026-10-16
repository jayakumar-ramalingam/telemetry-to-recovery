# Worker memory regression investigation

ID: rb-workers-memory@1.0
Owner: Demo platform team
Scope: demo/workers

This is synthetic scenario guidance, not evidence that a current incident exists.

Before proposing rollback, compare pre-release and post-release memory, restart
counts, arrival rate, processing capacity, queue age, and dependency health.
A new release followed by rising memory and restarts is a regression hypothesis,
not proof of a precise code defect. An increased arrival rate or downstream
saturation can require a different investigation.

If memory observations or the change history are absent, escalate. Never report
missing observations as healthy. Do not authorize recovery from a release
correlation alone.

Permitted proposal: rollback demo/workers from worker:v2 to worker:v1 as one bounded
trial, only if independent checks establish the scenario conditions. Prior-version
compatibility is declared by this teaching fixture, not established by the model.

Execution requires separate exact-plan approval, current-revision matching, fresh
evidence, an allowlisted target, no competing recovery, and DB utilization below
80%. The investigator cannot grant approval or execute the action.

Verify for 120 scenario seconds. The final 30 seconds must have queue age below
30 seconds, processing capacity above arrivals, p95 below 300 ms, no new restarts,
and DB utilization below 80%. If checks fail, escalate rather than trying more
aggressive actions automatically.
