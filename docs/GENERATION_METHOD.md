# SFPB instance generation method

## Common design

Both families use an ordered logical corridor with two directional halves. Logical stops are numbered from one end of the corridor, through the pair of city-centre nodes, to the other end. Terminals and city-centre nodes are mandatory; other stops can be mandatory or optional. The instance files provide stop-to-stop travel times, dwell times, a homogeneous vehicle fleet, an operating period, and pre-booked and dynamic requests. In the Leuven files, the second half returns over the same physical stops; in the Random files, the two halves have separately generated travel times and lie on either side of the centre.

The ten Leuven files vary fleet size, request mix, demand volume, promised pickup-window width, and request seed on one fixed Leuven corridor. The ten Random files use five synthetic corridors, with a narrow- and wide-window instance on each corridor. The exact settings appear in `INSTANCE_MANIFEST.csv`.

## Leuven

`generators/generate_leuven_instances.py` reads three supplied inputs:

1. `inputs/Leuven/reqreate_configuration.json` is the REQreate configuration, including the 25 physical stop locations, their mandatory/optional classes, and the candidate-demand distributions.
2. `inputs/Leuven/reqreate_request_pool.json` is the REQreate candidate request pool, with geographic origins and destinations, desired departure times, request timestamps, and booking types.
3. `inputs/Leuven/travel_time_matrix_seconds.json` contains the driving times in seconds between the 25 stops, computed in the same REQreate run on the OpenStreetMap street network. Rows are origins and columns destinations, both in configuration order; the matrix is not symmetric.

### Upstream REQreate step

The pool and the matrix come from one run of REQreate, an instance generator for demand-responsive transport (<https://github.com/michellqueiroz-ua/instance-generator>), at commit `d50f41a0` with local changes. The changes let REQreate read the mandatory/optional stop classes in the configuration, restrict the Leuven street network to a fixed bounding box, save the travel-time matrix between the configured stops, and generate requests in one process with Python's seeded random module. Unmodified REQreate rejects the supplied configuration. `reqreate/` contains the patch, the package versions of the original run, and the commands to repeat it.

The configuration requests one replica of 8,000 candidates for `Leuven, Belgium` with seed 42. Origins and destinations are drawn from the 25 named stops; a candidate needs a driving distance of at least 100 m and a positive driving time. The desired departure time (`earliest_departure`) follows a normal distribution with mean 09:00 and standard deviation one hour, restricted to 06:00–12:00. `is_prebooked` is drawn from a uniform distribution on [0, 1] and saved as the integer 0 or 1; the 4,053 candidates with value 1 are pre-booked. Pre-booked candidates have a lead time drawn uniformly from 1–3 days and dynamic candidates from 5–30 minutes; the request timestamp is the desired departure minus the lead time. REQreate also records a latest arrival (desired departure plus driving time plus ten minutes), which the generators do not use. Pool origins and destinations are `[latitude, longitude]`; instance coordinates are `[longitude, latitude]`.

The street network was downloaded on 21 January 2026, and the pool and matrix were generated on 18 April 2026. A new run downloads current OpenStreetMap data and can therefore give different travel times and candidates; the supplied files are the reference inputs of the instances.

### Instance construction

The script maps each physical stop to two logical stops, one per direction: logical stops 1–25 run outbound over physical stops 1–25, and logical stops 26–50 return over physical stops 25–1. The nine physical stops of the mandatory class give 18 mandatory logical stops, including both terminals and the centre pair 25/26.

Travel times are the source times converted to whole minutes by rounding down. As a result, 14 of the 48 links between consecutive distinct stops take 0 minutes, and a direct travel time can exceed the sum of two consecutive legs by at most one minute, which never exceeds the one-minute dwell at the intermediate stop. The script also replaces a source time that exceeds both five minutes and three times a straight-line estimate by that estimate; no entry of the supplied matrix meets this condition.

Each candidate is mapped to its nearest physical stops and to the direction in which its destination follows its origin. A candidate is kept if a vehicle that leaves the first terminal at 06:00 can reach the origin by the desired time, and a vehicle that leaves the origin at the desired time can complete the trip at least five minutes before 09:00; this check follows the mandatory stops with a one-minute dwell at each. A dynamic candidate must also be revealed between 06:00 and 09:00 and not after its desired time. Of the 8,000 candidates, 1,044 pre-booked and 1,034 dynamic candidates remain.

For each instance, the script draws the specified numbers of pre-booked and dynamic candidates without replacement using the instance's seed, orders them by request time, and numbers them from 0. Desired and request times are rounded down to whole minutes, and the pickup window is the desired time plus or minus the half-width. The script stops with an error if an instance asks for more requests than there are feasible candidates.

The Leuven files use request seed 42 for instances 01–08, seed 9 for 09, and seed 10 for 10. The operating period is 06:00–09:00, represented by minutes 360–540. Each vehicle has two indexed trips and capacity 20.

## Random

`generators/generate_random_instances.py` reads the ten structural profiles in `inputs/Random_profiles/`, the Leuven network and operating hours from `instances/Leuven/final_update_instance_01.json`, and the Leuven REQreate pool. Each profile is the structural part of an earlier synthetic instance, without its requests: stop count, fleet, operating period, request counts, pickup-window width, buffers, lead-time ranges, adjacent travel times, and mandatory stops. The generator uses the profile's adjacent travel times only for the total travel time of each half, and its mandatory stops only for the number of mandatory stops per half. The profiles are generator inputs, not study instances.

### Networks

Five corridor networks are generated using network seeds 7201–7205. Instance pairs 01/06, 02/07, 03/08, 04/09, and 05/10 share a network and differ in pickup-window half-width (5 or 10 minutes).

For each half, the script resamples Leuven's relative adjacent travel times to the target stop count with up to ±14% noise, scales them to the half's profile total (within ±4%), and allocates whole minutes of at least one to each link; the link between the two centre stops takes 0 minutes. A non-adjacent pair receives the sum of the adjacent times between its stops, reduced by a discount drawn independently for each pair from a uniform distribution on [0, 0.3] (`nonadj_discount`), rounded, and at least one minute.

Because the discounts are drawn independently, the travel times do not always satisfy the triangle inequality. Every trip visits all mandatory stops, so a vehicle travels directly only between stops of one segment between consecutive mandatory stops. On those pairs, a direct travel time exceeds the time through an intermediate stop, dwell included, by at most three minutes, and only in networks 01 and 04. Pairs that span a mandatory stop can deviate by up to 36 minutes but are never travelled directly.

The terminals and the two centre stops are always mandatory, and the number of mandatory stops per half comes from the profile (7, 9, 11, or 12). With at most nine per half, which is Leuven's number, the targets are Leuven's outbound mandatory positions (1, 8, 12, 13, 14, 17, 21, 24, and 25 of 25), subsampled when fewer are needed; with 11 or 12, the targets are evenly spaced. Each target is mapped to the nearest free stop. Both halves use the same positions counted from their first stop, so the second half is not mirrored as Leuven's return direction is.

The coordinates place the two halves on either side of a random centre near Leuven, along a gently curved line whose stop spacing is resampled from Leuven's geographic spacing. They are for inspection only, are not used to compute travel times, and do not represent actual streets.

### Requests

Requests are drawn with replacement from the feasible Leuven candidates of the same type, the same 1,044 pre-booked and 1,034 dynamic candidates as above. A candidate's origin and destination are converted to relative positions along its corridor half, and its desired time to a relative position in the Leuven operating period. These positions are mapped to the synthetic half with noise: up to ±0.025 of the half length for the stops, and Gaussian noise with a standard deviation of 3% of the operating period (at least one minute) for the desired time. A destination that does not follow its origin is moved to the next stop.

The desired time is limited to the range in which a vehicle that leaves the first terminal at the start of the operating period can reach the origin, and a vehicle that leaves the origin at the desired time can reach the destination and the last terminal before the end, with the buffers in the profile. The pickup window is the desired time plus or minus the half-width, limited to the operating period. A pre-booked request is revealed at the start of the operating period 1–30 days before the service day. A dynamic request is revealed at a minute drawn uniformly from 30 to 5 minutes before its desired time, but not before the operating period starts. Request IDs start at 1.

The packaged Random files use request seed 42. The option `--request-seed` draws another demand realization on the same five networks.

## Demand uncertainty and other events

Different request seeds create different demand realizations. Network structure, fleet, and operating profiles stay fixed when only the request seed changes. Travel times in each saved instance are fixed. Congestion variation, no-shows, cancellations, and other disruption events are not generated by these scripts.
