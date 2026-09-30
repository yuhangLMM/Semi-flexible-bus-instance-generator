# Rerunning the REQreate step

The instance generators do not need this step: the REQreate request pool and travel-time matrix are supplied in `inputs/Leuven/`. This folder documents how those two files were produced and how to repeat the run.

## What was used

| Item | Value |
| --- | --- |
| REQreate | <https://github.com/michellqueiroz-ua/instance-generator>, commit `d50f41a00f6588908da723d6fdd2a5f17a53974c` (18 November 2024, `master`) |
| Local changes | `reqreate_local_changes.patch` (five files under `REQreate/`) |
| Configuration | `inputs/Leuven/reqreate_configuration.json`, run as `REQreate/examples/my_cases/leuven_case_07/my_example_07.json` |
| Environment | Python 3.8.1 with the packages in `requirements.txt` |
| Street network | OpenStreetMap data downloaded by REQreate on 21 January 2026 and reused from its cache when the pool was generated on 18 April 2026 |
| REQreate license | MIT; the license text is in `LICENSE-REQreate` and applies to the REQreate code contained in the patch |

## Local changes

The supplied configuration does not run on unmodified REQreate. The patch makes these changes:

- `input_json.py` accepts the location classes `mandatory` and `optional` used in the configuration and adds these locations as stops; upstream accepts only `school`, `coordinate` and `bus_stop` and raises a `ValueError` for other classes. After loading the network, it computes the driving travel times between the 25 configured stops with REQreate's `_get_travel_time_matrix` and saves them as `forced_matrix.json` in the folder above the configuration folder. It also iterates over a copy of the attribute-graph nodes.
- `retrieve_network.py` downloads the Leuven street network inside a fixed bounding box (north 50.956415, south 50.860562, east 4.725156, west 4.668210) instead of the municipal boundary, so that the corridor is not cut at the boundary.
- `passenger_requests.py` generates the requests in the main process instead of as Ray tasks, and draws the random number for each sampled location with Python's seeded `random` module instead of NumPy's global generator. It also stops with a message when an attribute node has no type.
- `retrieve_bus_stations.py` starts Ray only when bus stations must be created, with a 2 GB object store.
- `REQreate.py` selects `Leuven, Belgium` and the configuration folder, and stops with a traceback when a configuration fails.

The remaining lines of the patch only reformat code.

## Steps

Use Python 3.8, as in the original run; several of the pinned versions are not available for Python 3.12 or later. In the commands below, replace `PACKAGE` with the path of this package.

```bash
git clone -c core.longpaths=true https://github.com/michellqueiroz-ua/instance-generator.git
cd instance-generator
git checkout d50f41a00f6588908da723d6fdd2a5f17a53974c
git apply PACKAGE/reqreate/reqreate_local_changes.patch
python -m venv .venv
source .venv/bin/activate
pip install -r PACKAGE/reqreate/requirements.txt
mkdir -p REQreate/examples/my_cases/leuven_case_07
cp PACKAGE/inputs/Leuven/reqreate_configuration.json REQreate/examples/my_cases/leuven_case_07/my_example_07.json
cd REQreate
python REQreate.py
```

On Windows, activate the environment with `.venv\Scripts\activate`, and in PowerShell create the folder and copy the configuration with:

```powershell
New-Item -ItemType Directory -Force REQreate\examples\my_cases\leuven_case_07
Copy-Item PACKAGE\inputs\Leuven\reqreate_configuration.json REQreate\examples\my_cases\leuven_case_07\my_example_07.json
```

The `core.longpaths` option lets Git check out upstream example files whose paths exceed the Windows limit. Start REQreate from the `REQreate/` folder, because the patched entry point reads the configuration from the relative path `./examples/my_cases/leuven_case_07/`.

The run writes the two files used by this package:

| REQreate output | Supplied file |
| --- | --- |
| `REQreate/Leuven, Belgium/json_format/my_example_07_1.json` | `inputs/Leuven/reqreate_request_pool.json` |
| `REQreate/examples/my_cases/forced_matrix.json` | `inputs/Leuven/travel_time_matrix_seconds.json` |

REQreate also writes CSV, pickle and image files, which this package does not use.

## Differences to expect

A new run downloads the current OpenStreetMap data. Street data change over time, so the travel times, and with them the candidate pool, can differ from the supplied files, which remain the reference inputs of the 20 instances. To build instances from a new pool, copy the two outputs over the files in `inputs/Leuven/` and run the generators; `generators/check_reproduction.py` then reports how the new instances differ from the packaged ones.
