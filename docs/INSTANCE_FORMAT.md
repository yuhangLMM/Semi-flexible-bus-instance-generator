# Instance format and information checklist

Each final instance is a JSON object with five model-input sections. Random instances also contain an optional `generation` section recording their random seeds and construction method.

| Section / field | Meaning and format |
| --- | --- |
| `config` | Scenario settings such as vehicle count, operating bounds, demand counts, and pickup-window width. Available keys differ between Leuven and Random; see the notes below. |
| `network.stops` | Ordered logical stop IDs, starting at 1. |
| `network.mandatory_stops`, `optional_stops` | Logical stop IDs by service type. Treat them as sets: the Leuven files keep the unsorted order of the study files. |
| `network.terminals`, `city_center` | Two terminal IDs and the two logical city-centre IDs. |
| `network.coordinates` | `{stop_id: [longitude, latitude]}`. Leuven coordinates are the configured stop locations, with the return direction offset by 0.0001° in longitude and latitude; Random coordinates are synthetic. |
| `network.travel_times` | `{ "origin_id,destination_id": minutes }` in whole minutes. Leuven supplies both directions for distinct stop IDs; Random supplies forward-ordered pairs (`origin_id < destination_id`). These are travel times, not distances or speeds. `GENERATION_METHOD.md` describes their rounding and where they depart from the triangle inequality. |
| `network.dwell_times` | `{stop_id: minutes}` for stop dwell. |
| `fleet.vehicles` | Vehicle ID list. Vehicles share the capacity in `fleet.capacity`. |
| `fleet.trips` | Trip indices for each vehicle; these are not scheduled departure times. |
| `requests.prebooked`, `requests.dynamic` | Maps from request ID to passenger-request records. |
| `parameters.operating_hours` | Service-period start and end in minutes. |
| `parameters.promise_window` | Pickup-window allowances in Leuven. The corresponding Random width is in `config.pb_half_width`. |
| `parameters.rejection_penalty` | Penalty used by the study model. |
| `parameters.visualize`, `output_path` | Leuven only: settings of the study's experiment runner, not model input. |
| `generation` | Random-instance provenance, including network and request seeds. It is descriptive metadata. |

Each request record contains `id`, `type`, `origin`, `destination`, `desired_time`, `time_window: [earliest, latest]`, and `request_time`. Stop references use logical stop IDs. All time values use minutes on a common service-day time axis: 360 denotes 06:00. A pre-booked `request_time` may be negative because it can represent a request made days before the service day. Request IDs are unique within an instance; they start at 0 in Leuven and at 1 in Random.

The Leuven `config` holds the operating bounds, vehicle count, and vehicle capacity. The Random `config` holds the profile settings used by the generator: the number of stops per half (`n_stops`), fleet, request counts, operating bounds, pickup-window half-width (`pb_half_width`), dwell time, the upper bound of the non-adjacent discount (`nonadj_discount`), the start, destination, and terminal buffers, the dynamic lead-time range (`dyn_time_threshold` to `max_dyn_lead` minutes), the pre-booking range in days, and `random_seed`, which equals the request seed. `adj_low`, `adj_high`, and `mandatory_ratio` are settings of the earlier synthetic instances from which the profiles were taken. The generator does not use them, and they do not describe the saved networks; the actual travel times and mandatory stops are in `network`.

## Available instance information

| Requested information | Supplied representation | Boundary |
| --- | --- | --- |
| Network nodes, node types, and links | Ordered logical stops; mandatory/optional classes; terminals and centre; coordinates; stop-pair travel times and dwell times | The JSON is a service-level corridor representation. It has no separate road-edge list, explicit road distance, or speed field. |
| Bus routes and timetable | Corridor stop order, direction, vehicle and trip indices, and operating period | There is no fixed departure timetable, headway table, or per-vehicle route schedule in the instance input. |
| Vehicles | Vehicle IDs, common capacity, and trip indices | No vehicle-specific types or heterogeneous attributes are included. |
| Request generation | REQreate configuration, candidate pool and travel-time matrix; the REQreate patch and package versions; both instance generators; random seeds; and saved pre-booked/dynamic request records | The REQreate configuration defines the upstream Leuven candidate-demand distributions; Leuven draws from that pool, and Random maps Leuven-derived patterns onto synthetic corridors. |
| Uncertainty generation | Seeded demand realizations and dynamic request-revelation times | Congestion, no-shows, cancellations, and travel-time shocks are not modeled in these instance files. |
| Other model data | Operating period, pickup windows, dwell times, and rejection penalty | Optimization results and algorithm traces are separate from instance input. |
