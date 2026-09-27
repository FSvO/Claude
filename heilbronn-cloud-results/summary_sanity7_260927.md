# Heilbronn triangle certification summary: n = 7, target = 0.04861597222222222

| case | part | prefix | verdict | status | runtime (s) | upper bound | best found |
|---|---|---|---|---|---|---|---|
| boundary | 0 |  | PROVED | OPTIMAL | 4 | 0.04861134844453912 | 0.04861134844453912 |
| boundary | 1 |  | PROVED | BOUND_REACHED | 2 | 0.04801640332215361 | 0.0421835178139196 |
| boundary | 2 |  | PROVED | BOUND_REACHED | 3 | 0.048347924981443836 | 0.04245699048251017 |
| boundary | 3 |  | PROVED | BOUND_REACHED | 2 | 0.04754402586842173 | 0.04376757164856343 |
| boundary | 4 |  | PROVED | BOUND_REACHED | 3 | 0.048580244405009916 | 0.043767769909461164 |
| boundary | 5 |  | PROVED | OPTIMAL | 2 | 0.048611900654842194 | 0.048611900654842194 |
| boundary | 6 |  | PROVED | OPTIMAL | 4 | 0.04861159777956059 | 0.04861159777956059 |
| boundary | 7 |  | PROVED | BOUND_REACHED | 10 | 0.048615884677346656 | 0.04861159114138496 |
| vertices | 0 |  | PROVED | BOUND_REACHED | 1 | 0.04716993979718759 | 0.034785456541207814 |

Verdict counts: {'PROVED': 9}

Boundary case fully covered by proved parts: True
Corners-occupied case proved: True
All results use the same n and target: True
**CERTIFIED (subject to the model assumptions in README): every configuration of n = 7 points in the unit right triangle has minimum triangle area <= 0.04861597222222222.**
