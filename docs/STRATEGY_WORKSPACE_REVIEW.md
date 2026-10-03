# Strategy workspace review

Reviewed on 2026-10-04. Priority: plan ERS use and race scenarios. Lap analysis is outside the reconstruction scope.

## Implemented on 2026-10-04

The Track plan layout is now implemented at `/strategy`. Race, comparison and qualifying use a shared model and background job/cache infrastructure. The UI separates energy and geometry readiness, keeps an explicit Build plan action, and links forecast, battery curve and map to the same selected result. Old strategy URLs redirect here; session reports and corner definitions are supporting tools.

The initial audit findings below describe the old screens. Reconstruction replaced their competing race engines, validated measured energy inputs, excluded incompatible known conditions and physically contradictory actions, conserved section-boundary timing/SOC, and enforced reserve and comparison endpoint constraints. Energy forecasting remains unvalidated in-game and excludes pits, traffic, weather changes and full-race tyre planning.

## Recommendation

Use two main workspaces: **Lap analysis** and **Strategy**. Put recording/session selection and track tools in contextual controls. Keep a session library accessible from the shared session picker; a separate Session analysis navigation item is unnecessary for this priority.

Strategy should answer three questions in one place:

1. Where should I deploy or recover energy on the next lap?
2. What happens to battery reserve over the next few laps?
3. Which alternative is faster under comparable battery constraints?

Use **Race energy**, **Scenario comparison**, and **Qualifying energy** as local modes sharing the same session, edition, track, reference lap, evidence, and plan output. They should not each be global pages with unrelated defaults.

## Current screens and their better forms

| Current screen | Useful contribution | Recommended form |
| --- | --- | --- |
| ERS Strategy | Track action locations, SOC projection, deployment comparisons, multi-lap planning | The basis of the Strategy workspace; show one selected plan consistently across every view |
| Qualifying strategy | Run-up, timing-line and finish battery constraints | Qualifying energy mode inside Strategy |
| Archived Race strategy | Short-horizon battery scheduling | Replace its separate interface and retire its older planner after validation against the selected shared engine |
| Operation Library | Representative pedal pattern and section definitions from saved laps | Track reference / Evidence panel inside Strategy; frequency of an action is not proof that it is optimal |
| Session analysis | Post-run comparisons and consistency review | A session report reached from the session picker, or a contextual post-run validation panel; repair the position contract first |
| Map & Corners | Track/corner definitions | Edit track action beside the map; request setup only when the selected feature actually needs it |

## Proposed interaction

1. Choose a session and reference lap once. Show the automatically detected edition beside them. Historical laps used as supporting evidence must remain visible and edition-compatible.
2. Choose a goal: Race energy, Compare scenarios, or Qualifying energy.
3. Set starting battery and reserve. Race energy adds remaining laps and a 3–5 lap horizon. Qualifying adds run-up and timing-line requirements.
4. Build the plan explicitly. Use one background job and cached model shared by all views. Mark edited controls as pending until recalculation completes.
5. Display the next-lap distance strip / action map and battery curve together. Beside them, show the horizon projection and the actual assumptions used.
6. Keep source laps, empirical associations, inferred effects, and advanced filtering in an Evidence panel. Compare the planned result with the next recorded lap before trusting repeated predictions.

A map is optional. When valid positions are unavailable but distance and energy data are usable, keep the distance strip and battery projection available, with a clear map-unavailable state.

## Reliability findings from the current checkout

- `backend/lap_recorder.py` writes `position.x` and `position.z`. `backend/session_analysis.py::_position` requires x, y, and z; `_reference_line` rejects a lap without enough XYZ samples. A read-only audit found 381 saved laps with X/Z fields and only 205 with any complete XYZ samples. Thus 176 cannot supply the currently required reference line. Counted field availability, not proof that the other 205 have valid geometry.
- All nine recorded laps in the latest 2026-10-03 session have only one distinct X/Z pair. The earlier decoder correction cannot recover lost positions in those recordings. A metadata-only “ready” flag must not imply that their maps are usable.
- `backend/operation_sections.py::build_operation_library` selects by validity, pit status, lap time, sample count and track length. It does not partition by edition, tyre, fuel, setup or weather. A representative pattern can therefore mix incompatible conditions. The strategy model itself filters to the 2026 edition, but the standalone library does not.
- `backend/app.py` marks ERS courses ready using metadata counts. Actual battery samples, action coverage, geometry, and comparable conditions need separate checks.
- Race strategy uses `backend/race_optimizer.py`; ERS Strategy uses `backend/strategy_scenarios.py::optimize_multi_lap_strategy`. They are different planners over a shared section model. On the same 16-lap Imola model, 60% start, three-lap horizon, eight laps remaining and a 10% reserve setting, their predicted end reserves were approximately 46% and 23.29%. A single interface must not silently choose between these conflicting results.
- The older race planner forces save-lap recovery to at least 3%, adds a fixed 220 ms cost, and uses fixed tyre/fuel estimates. These are model assumptions rather than learned race physics.
- In that Imola model, 49 of 162 section/action entries were tagged observed, 104 inferred, and 9 inferred baseline. These are entries, not independent laps or calibrated accuracy percentages. Observed section medians are associations; whole-lap pace normalization does not isolate the causal effect of deployment or lifting.
- The existing “same finish SOC” comparison can produce a nearby rather than identical endpoint. In the Imola 60% example, the target was 47.75%, deployment-only ended at 47.14%, and lift+deployment at 47.73%. Show endpoint differences and enforce a stated tolerance before ranking comparisons as equivalent.
- Current prediction modules model short-horizon energy use. They do not provide a validated pit-stop, traffic, weather or full-race tyre simulation. Name the current scope **Race energy**. Broader race scenarios need those additional models and evidence before appearing as recommendations.

## Readiness and evidence

Display independent states for:

- **Edition/rules:** detected automatically; current strategy model supports the 2026 edition. Detection of 2025 does not imply that 2026 action rules can be applied to it.
- **Energy:** enough valid distance, time, battery and mode samples for the requested plan.
- **Geometry:** moving, plausible X/Z positions for a map. Missing Y can support a clearly labelled planar review; do not fabricate measured elevation.
- **Comparison:** comparable conditions, source coverage and battery endpoint tolerance.
- **Prediction:** measured association versus inferred effect, with unvalidated assumptions disclosed near the result.

Do not turn raw lap counts, action frequency or existing heuristic confidence values into a percentage claiming predictive accuracy.

## Reconstruction sequence

1. Repair readiness checks and the recorder/session-analysis position contract. Validate model inputs and physical plausibility before presenting an actionable recommendation.
2. Select and validate one race-energy engine. Keep qualifying constraints as a separate objective over the same evidence/model infrastructure. Add regression cases for reserve, horizon, infeasibility, endpoint tolerance and edition isolation.
3. Add a unified Strategy route and shared context; move existing useful components into local modes and supporting panels. Preserve old URLs as redirects/deep links.
4. Remove duplicate navigation, divergent mode selectors and implementation-first headings such as Phase 1 / DP / MPC. Show one explicit calculation state and one selected plan.
5. Verify saved-data and no-map states in the browser, then rebuild and test the Windows package before describing Windows and GitHub as synchronized.

The initial layout proposal used saved Imola laps. The implemented workspace uses recalculated, condition-matched source data and reports inferred effects separately. Browser and package validation details belong in the release change log.
