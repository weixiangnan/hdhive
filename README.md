# Site SignIn Plugins

MoviePilot V2 standalone plugins for HDHive and HostLoc sign-in / points tasks.

## Repository layout

- `package.v2.json`
- `plugins.v2/hdhivesignin/__init__.py`
- `plugins.v2/hostlocsignin/__init__.py`
- `plugins.v2/nodeseeksign/__init__.py`

## Install

Add this repository to your MoviePilot V2 third-party plugin sources, then install the plugin you need.

Available plugins:

- `HDHive 自动签到`
- `HostLoc 自动签到`
- `NodeSeek论坛签到`

## Configure

### HDHive

- `站点地址`: default `https://hdhive.com/`
- `Cookie`: full logged-in browser cookie
- `用户名/密码`: optional, used for auto login when Cookie is missing/expired
- `User-Agent`: browser UA matching the cookie
- `定时执行周期`: optional cron
- `立即运行一次`: save once to test

### HostLoc

- `站点地址`: default `https://hostloc.com/`
- `Cookie`: full logged-in browser cookie
- `User-Agent`: browser UA matching the cookie
- `多账号配置`: optional, one account per line using `username----password`
- `访问空间次数`: default `10`
- `自定义空间链接`: optional, one per line
- `定时执行周期`: optional cron
- `立即运行一次`: save once to test

### NodeSeek

- `Cookie`: NodeSeek 登录 Cookie
- `签到周期`: optional cron

## Notes

The plugins are independent and do not depend on `AutoSignIn`.
