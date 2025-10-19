NetCommand
=========

Command line tool to manage and update various (network) devices in batches from command line.

Usage
=====

Create your own inventory, see sample_inventory.yaml for reference

batch commands
---

```shell
./netcommand.py [-d] [-l|--limit hostname|group[,hostname2|group2...]] [-C|--dry-run] [-K] inventory.yaml commands commands.txt
```

batch update
---

Download update images to local "imagedir" and/or configure remote server in inventory.

Image name format is defined per model but generally format is `{prefix}{model}-{platform}-{version}.suffix`.
For example routeros-arm64-7.10.2.npk or os10-Enterprise-10.1.2.345.bin


```shell
./netcommand.py [-d] [-l|--limit hostname|group[,hostname2|group2...]] [-C|--dry-run] [-K] inventory.yaml update version
```

Environment variables
---

Environment variables override values from inventory file.

`SSH_KEY_PASSWORD` is used to open ssh key.

`SSH_PASSWORD` is used while connecting to devices. Overrides opts.password variable.

Supported operating systems:
---

| Model name | OS                | Commands | Upgrade |
|------------|-------------------| -- | -- |
| routeros   | Mikrotik RouterOS | Yes | Yes |
| delln      | Dell N-series     | Yes | Yes |
| dellos10   | Dell OS10         | Yes | Partial* |
| ios        | Cisco IOS         | Yes | No |

*  Dell OS10 upgrade downloads and installs the upgrade image but needs to be reloaded manually.


License
=======

The MIT License (MIT)

Copyright (c) 2023 Antti Jaakkola

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
