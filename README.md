# openhasp-config-manager

A cli tool to manage all of your [openHASP](https://github.com/HASwitchPlate/openHASP) device configs in a centralized
place.

# Features

* [x] unlimited multi-device management
* [x] shared configuration between devices
* [x] jsonl preprocessing, which allows for
    * [x] `//` comments within jsonl files
    * [x] line breaks wherever you like
    * [x] jinja2 templating within object values
    * [x] local and globally scoped variables
  * [x] default theming for all object types
* [x] validation of common mistakes for
    * [x] jsonl objects
    * [x] cmd files
* [x] simple configuration upload to the device(s)
    * [x] automatic diffing to only update changed configuration files
    * [x] git-style diff output for changed lines
* [x] GUI Preview (WIP)
    * [x] Inspect individual plate screens before deploying to an actual device
    * [x] Speedup prototyping by using the preview to test your changes
* [x] API client (Web + MQTT)
    * [x] execute commands on a plate
    * [x] listen to events and state updates

```shell
> openhasp-config-manager -h
Usage: openhasp-config-manager [OPTIONS] COMMAND [ARGS]...

Options:
  --version   Show the version and exit.
  -h, --help  Show this message and exit.

Commands:
  cmd         Sends a command request to a device.
  deploy      Combines the generation and upload of a configuration.
  generate    Generates the output files for all devices in the given...
  help        Show this message and exit.
  listen      Sends a state update request to a device.
  logs        Prints the logs of a device.
  screenshot  Requests a screenshot from the given device and stores it...
  shell       Connects to the telnet server of a device.
  state       Sends a state update request to a device.
  upload      Uploads the previously generated configuration to their...
  vars        Prints the variables accessible in a given path.
```

# Disclaimer

**TL;DR: This project is still experimental.**

I do use openhasp-config-manager exclusively to configure all of my openHASP devices. I am in the
process of adding tests to everything to make it more reliable and have also added lots of features along the way.
However, there are definitely still a couple of things that do not yet work as intended. Error logs
might need some love to be able to figure out what you did wrong. If you like the
project, feel free to open an issue or PR to help me out.

# How to use

## Docker

```
docker run -it --rm \
  --name openhasp-config-manager \
  --user 1000:1000 \
  -v "./openhasp-configs:/app/openhasp-configs" \
  -v "./output:/app/output" \
  ghcr.io/markusressel/openhasp-config-manager
```

## Installation

Since openhasp-config-manager needs some dependencies (see [here](/pyproject.toml)) it is
**recommended to install it inside a virtualenv**.

### venv-install

[venv-install](https://github.com/markusressel/venv-install) is a little helper tool to eas the
installation, management and usage of python cli tools in venvs.

```bash
venv-install openhasp-config-manager openhasp-config-manager
openhasp-config-manager -h
```

### Manual

```bash
mkdir -p ~/venvs/openhasp-config-manager
python3 -m venv ~/venvs/openhasp-config-manager
source ~/venvs/openhasp-config-manager/bin/activate
pip3 install openhasp-config-manager
```

And to use it:

```shell
source ~/venvs/openhasp-config-manager/bin/activate
openhasp-config-manager -h
openhasp-config-manager analyze -c "./openhasp-configs"
...
```

### Uninstall

```bash
deactivate
rm -rf ~/venvs/openhasp-config-manager
```

## Configuration

openhasp-config-manager is first and foremost a configuration
management system. Simply follow the basic folder structure and
config deployment will become trivial. **Please read all of this,
as it is very important to understand the basic structure on
which everything relies.**

### Folder Structure

The following folders should reside inside a single parent
folder, f.ex. named `openhasp-configs`. This folder can be
located anywhere you like, but must be accessible to
openhasp-config-manager when executing.

* `common`: The `common` subdirectory can be used for files
  that should be included on _all_ device. This folder is optional.
* `devices`: The `devices` folder is required. It must contain one
  subfolder for each openHASP device you want to configure using
  openhasp-config-manager. It is recommended to name subfolders according
  to the physical devices associated with them.
    * `touch_down_1` (example device folder)
        * A device folder contains `*.jsonl`, `*.cmd` and other files which should
          only be uploaded to that particular device.
        * You can create arbitrary nested folder structures for organizing the files.
          There is a limit to the file name length though,
          see [FAQ](#output-file-name-length-must-not-exceed-30-characters)
        * You must provide a `config.json` file, see [config.json](#config.json)
          for more info.

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

openhasp-config-manager makes use of the `config.json` on your plate. It can extract information
from it to detect things like screen orientation, and also allows you to deploy changes within the
`config.json` file. Since [the official API does not support
uploading the full file](https://github.com/HASwitchPlate/openHASP/issues/363), only settings
which can also be set through the web ui on the plate itself are currently supported.

To retrieve the initial version of the `config.json` file you can use the
built-in file browser integrated into the webserver of your openHASP plate, see
[official docs](https://www.openhasp.com/latest/faq/?h=web#is-there-a-file-browser-built-in).

The official `config.json` file doesn't provide enough info for openhasp-config-manager
to enable all of its features though. To fix that simply add a section to the
file after downloading it:

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

### Config File Preprocessing

openhasp-config-manager runs all configuration files through various preprocessors, which allow us to use
features the original file formats do not support by themselves, like f.ex. templating.

#### Multiline JSONL files

While the JSONL file format requires each object to be on a single line, openhasp-config-manager
allows you to add as many line breaks as you wish. This makes it much easier to edit, since a config
like this:

```json
{
  "page": 0,
  "id": 31,
  "obj": "msgbox",
  "text": "%ip%",
  "auto_close": 5000
}
```

will be deployed like this:

```json lines
{
  "page": 0,
  "id": 31,
  "obj": "msgbox",
  "text": "%ip%",
  "auto_close": 5000
}
```

#### Comments

Neither JSON nor JSONL allows comments, but openhasp-config-manager does!
You can mark comments by prefixing them with a double forward-slash:

```json5
// File description
{
  // Object Description
  "page": 0,
  "id": 31,
  // Property Description
  "obj": "msgbox",
  "text": "%ip%",
  "auto_close": 5000
}
```

#### Templating

You can use Jinja2 templates inside all jsonl object values. To access the value of another object in a
template, you can use the `pXbY` syntax established by openHASP, where `X` is the `page` of an object and
`Y` is its `id`. openhasp-config-manager even tries to resolve templates that lead to other templates.
Be careful not to create loops in this way though.

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
be referenced inside of templates. Variables are defined using `*.yaml` files. If you
decided to use a subfolder structure to organize your configuration files you can use these folders
to also set the scope of variables. More specific variable definitions (longer path) will override
less specific ones.

##### Global

Global variables can be specified by creating `*.yaml` files inside the root config folder (f.ex. `openhasp-configs`).

Example:

`openhasp-configs/global.vars.yaml`

```yaml
about:
  page_title: "About"
```

To access this variable, use a Jinja2 template:

`openhasp-configs/common/about_page.jsonl`

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
of a `device` folder.

> **Note**
>
> Device specific variables will override global variables, given the same name.

Example:

`openhasp-configs/device/my_device/device.vars.yaml`

```yaml
page_title: "My Device"
```

`openhasp-configs/device/my_device/some_folder/some_page.jsonl`

```json lines
{
  "page": 1,
  "id": 1,
  ...
  "title": "{{ page_title }}",
  ...
}
```

`openhasp-configs/device/my_device/some_other_folder/some_page.jsonl`

```json lines
{
  "page": 2,
  "id": 1,
  ...
  "title": "{{ page_title }}",
  ...
}
```

#### Printing variables

If you are not sure what variables are accessible in a given path, you can use the `vars`
command, which will give you a copy&paste ready output of all variables for a
given directory:

```shell
> openhasp-config-manager vars -c openhasp-configs -p devices/touch_down_1/home
common.navbar.first_page: 1
common.navbar.last_page: 4
...
header.title: Home
```

#### Theming

To specify default property values for an object type, simply define them as a variable
under `theme.obj.<obj-type>`, where `<obj-type>` is the value of the `obj` property of the object.

The keys used must conform to the naming of the object properties as specified in OpenHasp, see:
https://www.openhasp.com/latest/design/objects/

F.ex., to make the background color of all buttons red by default, define:

```yaml
theme:
  obj:
    btn:
      bg_color: "#FF0000"
```

in a global variable file named `theme.yaml` located at the root of your configurations directory
`openhasp-configs/theme.yaml`.

## Deployment

To deploy your configurations to the already connected openHASP devices, simply use the
`generate`, `upload` or `deploy` commands of `openhasp-config-manager`.

> **Note**
> openhasp-config-manager needs direct IP access as well as an enabled webservice on the plate
> to be able to deploy files to the device. To enable the webservice
> try: `openhasp-config-manager cmd -d plate35 -C service -p "start http"`

## Run commands

While openhasp-config-manager is first and foremost a config management system,
it also allows you to run commands on a device by issuing MQTT messages without the need to install a separate
MQTT client first. Note that the MQTT _server_ still needs to be running and also has to
be reachable from your local machine for this to work.

For a list of possible commands to send to a device, take a look at the official
documentation: https://openhasp.haswitchplate.com/latest/commands/

```shell
> openhasp-config-manager cmd -c ./openhasp-configs -d plate35 -C backlight -p "{\"state\":\"on\",\"brightness\":128}"
```

# FAQ

## How do I see device logs?

Try the `logs` command (this does require network access to the device):

```shell
> openhasp-config-manager logs -d plate35
```

If that doesn't work, open a terminal and run the following command with the device connected via USB cable:

```shell
bash -c "screen -q -L -Logfile device.log /dev/ttyUSB0 115200 &> /dev/null; tail -F device.log; killall screen"
```

## Output file name length must not exceed 30 characters

If you want to organize your files (both common and device-specific ones) you can
simply create subfolders to achieve your desired structure. However, due to a technical
limitation openHASP does not support subfolder on the actual device. To overcome
this limitation openhasp-config-manager will automatically generate a file name for
files in subfolders before uploading them to the device. `.json` or `.cmd` files within subfolders
will be renamed by concatenating their full subpath using an underscore (`_`) as a separator. So f.ex.
the file in the following structure:

```text
openhasp-configs
└── devices
    └── touch_down_1
        └── 0_home
            └── 0_header.jsonl
```

would be uploaded to the `touch_down_1` device with the name `0_home_0_header.jsonl`.

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
