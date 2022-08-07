# openhasp-config-manager

A tool to manage all of your [openHASP](https://github.com/HASwitchPlate/openHASP) device configs in a centralized place.

# Features

* [x] manage as many devices as you like
* [x] share configuration files between devices
* [x] jsonl preprocessing, which allows for
  * [x] `//` comments within jsonl files
  * [x] line breaks wherever you like
  * [x] jinja2 templating within object values
* [x] output validation
  * [x] no more weird behavior due to invalid "id" range
* [x] one click configuration upload to the device
  * [x] automatic diffing to only update changed configuration files
* [x] execute commands directly from the CLI (still needs a connection to the MQTT broker)

# How to use

## Installation

Since openhasp-config-manager needs some dependencies (see [here](/pyproject.toml)) it is
recommended to install it inside of a virtualenv:

```
python3 -m venv ~/path/to/new/virtual/environment
source ~/path/to/new/virtual/environment/bin/activate
pip3 install openhasp-config-manager
```

## Configuration

openhasp-config-manager is first and foremost a configuration
management system. Simply follow the basic folder structure and
config deployment will become trivial.

* `devices`: In the root directory of your configuration, a folder called
  `devices` is expected.
  * In there you can create as many subfolders as
    you like, naming them according to the physical devices that you
    want to manage.
    * Within those device subfolders you can then create
      `*.jsonl` and `*.cmd` files.
    * You must also provide a `config.json` file, see [config.json](#config.json)
      for more info on how to set it.
* `common`: The `common` directory can be used to put files
  that should be included on _all_ device.

You are not limited to a folder depth of one. However, the files
on OpenHasp devices cannot be put into subfolders. Therefore, if you put
`.json` or `.cmd` files into subfolders, the name of the
resulting file on the OpenHasp device will be a concatenation of
the full subpath using an underscore (`_`) as a separator. So f.ex.
the file in the following structure:

```text
openhasp-configs
└── devices
    └── touch_down_1
        └── 0_home
            └── 0_header.jsonl
```

would only be uploaded to the `touch_down_1` device and named:
`0_home_0_header.jsonl`

A more advanced configuration layout could look something like this:

```text
openhasp-configs
├── common
│   ├── content
│   │   └── card.jsonl
│   ├── dialog
│   │   ├── connected.jsonl
│   │   └── offline.jsonl
│   ├── navigation_bar.jsonl
│   └── page_header.jsonl
└── devices
    └── touch_down_1
        ├── 0_home
        │   ├── 0_header.jsonl
        │   ├── 1_content.jsonl
        │   └── page.cmd
        ├── 5_about
        │   ├── 0_header.jsonl
        │   ├── 1_content.jsonl
        │   └── page.cmd
        ├── boot.cmd
        ├── config.json
        ├── offline.cmd
        └── online.cmd
```

### config.json

openhasp-config-manager makes use of the `config.json` on your plate. It can use information 
to detect things like screen orientation, and also allows you to deploy config changes to your
plate when you make changes in the config.json file. Since [the official API does not support
uploading the full file](https://github.com/HASwitchPlate/openHASP/issues/363), only settings 
which can also be set through the web ui on the plate itself are currently supported.

To retrieve the initial version of the `config.json` file you can use the
built-in file browser integrated into the webserver of your OpenHASP plate.

The official `config.json` file doesn't provide enough info for openhasp-config-manager
to enable all of its features though. To fix that openhasp-config-manager looks for an 
additional section within the file which is not present by default:

```json
{
  "openhasp_config_manager": {
    "device": {
      "ip": "192.168.5.134",
      "screen": {
        "width": 320,
        "height": 480
      }
    }
  },
  "wifi": {
    "ssid": "Turris IoT",
    ...
  }
```

Simply add this section to the `config.json` after you have retrieved it from
the plate.

### Preprocessing

openhasp-config-manager runs all configuration files through a preprocessor, which allows us to use
features the original file format doesn't support, like f.ex. templating.

#### Templating

You can use Jinja2 templates inside of values. You can access each of the objects using the
`pXbY` syntax established by OpenHASP, where `X` is the `page` of an object and `Y` is its `id`.

You can use the full functionality of Jinja2 like f.ex. math operations, function calls or type conversions.

```yaml
{
  "page": 1,
  "id": 1,
  "x": 0,
  "y": 0,
  ...
}

{
  "page": 1,
  "id": 2,
  "x": "{{ p1b1.x }}",
  "y": "{{ p1b1.y + 10 }}",
  ...
}
```

#### Variables

Besides accessing other objects, you can also define custom variables yourself, which can then
be used inside of templates.

##### Global

Global variables can be specified by creating `*.yaml` files inside of the `common` folder.

Example:

`common/global.vars.yaml`

```yaml
about:
  page_title: "About"
```

`common/about_page.jsonl`

```json lines
{
  "page": 9,
  "id": 1,
  ...
  "title": "{{ about.page_title }}",
  ...
}
```

##### Device specific

Device specific variables can be specified by creating `*.yaml` files inside any of the sub-folders
of the `device` folder.

> **Note**
>
> Device specific variables will override global variables, given the same name.

Example:

`device/my_device/device.vars.yaml`

```yaml
page_title: "My Device"
```

`device/my_device/some_folder/some_page.jsonl`

```json lines
{
  "page": 1,
  "id": 1,
  ...
  "title": "{{ page_title }}",
  ...
}
```

`device/my_device/some_other_folder/some_page.jsonl`

```json lines
{
  "page": 2,
  "id": 1,
  ...
  "title": "{{ page_title }}",
  ...
}
```

## Deployment

To deploy your configurations to the already connected OpenHASP devices, simply use the
command line tool `openhasp-config-manager`:

```shell
> openhasp-config-manager                                                         0 (0.604s) < 02:11:38
Usage: openhasp-config-manager [OPTIONS] COMMAND [ARGS]...

Options:
  --version   Show the version and exit.
  -h, --help  Show this message and exit.

Commands:
  cmd       Sends a command request to a device.
  deploy    Combines the generation and upload of a configuration.
  generate  Generates the output files for all devices in the given...
  upload    Uploads the previously generated configuration to their...
```

## Run commands

OpenHasp allows you to run commands on a device by issuing MQTT messages.
While openhasp-config-manager is first and foremost a config management system,
it also allows you to run commands on a device without the need to install a separate
MQTT client first. Note that the MQTT _server_ does need to be running and also has to
be reachable from your local machine.

See: https://openhasp.haswitchplate.com/latest/commands/

```shell
> openhasp-config-manager cmd -c ./openhasp-configs -d plate35 -C backlight -p "{\"state\":\"on\",\"brightness\":128}"
```

# Contributing

GitHub is for social coding: if you want to write code, I encourage contributions
through pull requests from forks of this repository. Create GitHub tickets for
bugs and new features and comment on the ones that you are interested in.

# License

```text
openhasp-config-manager is free software: you can redistribute it and/or modify
it under the terms of the GNU AFFERO GENERAL PUBLIC LICENSE as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
