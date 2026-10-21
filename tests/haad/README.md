# Tests of the haad integration

`openhasp_config_manager/haad` is used by haad projects (e.g. `haad-home`) and needs haad, which needs Python 3.14. These tests run in
haad's uv environment (`../haad`, checked out next to this repository), with 100 % line and branch coverage:

```shell
make test-haad
```

- `fakes.py`: `FakePlate`, the device side of a plate. The real `OpenHaspClient`, `MqttClient` and `WebserviceClient` are used, only
  their network layers are replaced, so the tests pin the exact traffic (topics, payloads, HTTP requests).
- `conftest.py`: plate controllers on haad's `simulator` fixture (simulated time, Home Assistant and MQTT), with `config_dir` pointing
  to `tests/_test_cfg_root`.
- `scenario_test.py`: golden masters, one page per page shape of haad-home.
- `layout/`, `page_api_test.py`, `owned_plate_test.py`, `device_factory_test.py`, `parity_test.py`: the code-defined layouts
  (`openhasp_config_manager/haad/layout/README.md`).

The tests pin the current behaviour, bugs included (see `openhasp_config_manager/haad/layout/QUESTIONS.md`). Fixing one is its own
change that updates its test on purpose.
