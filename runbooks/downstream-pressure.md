# Downstream pressure and scaling

ID: rb-downstream-pressure@1.0
Owner: Demo data services team
Scope: demo/workers

This is guidance, not a current observation.

Before adding workers, inspect downstream utilization, connection pressure,
arrival rate, and the processing bottleneck. More worker callers may increase
database demand. A restart or rollout does not prove recovery.

This teaching executor does not permit scale-out. Its linear database-utilization
multiplier is an illustrative risk screen, not a calibrated capacity model.

If database utilization reaches 80%, the recovery executor must stop. If the
evidence cannot distinguish a worker regression from dependency saturation,
request human investigation. No shell commands, database changes, or wider-scope
operations are allowed by this runbook.
