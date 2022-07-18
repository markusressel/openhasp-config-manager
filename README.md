# openhasp-config-manager

A tool to manage all of your [openHASP](https://github.com/HASwitchPlate/openHASP) device configs in a centralized place.

# Features

* [x] manage as many devices as you like
* [x] share configuration files between devices
* [x] jsonl preprocessing, which allows for
  * [x] `//` comments within jsonl files
  * [x] line breaks wherever you like
* [x] one click configuration upload to the device
  * [x] automatic diffing to only update changed configuration files
* [x] execute commands directly from the CLI (still needs a connection to the MQTT broker)

# How to use

openhasp-config-manager is first and foremost a configuration
management system. Simply follow the basic folder structure and
config deployment will become trivial.

## Configuration

* `devices`: In the root directory of your configuration, a folder called
  `devices` is expected. In there you can create as many subfolders as
  you like, naming them according to the physical devices that you
  want to manage.
* `common`: The `common` directory can be used to put files
  that should be included on _all_ device.

You are not limited to a single folder level. However, the files
on OpenHasp devices cannot be put into subfolders. If you put
`.json` or `.cmd` files into subfolders, the name of the
resulting file on the OpenHasp device will be a concatenation of
the full subpath. So f.ex. the file in the following structure:

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
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
