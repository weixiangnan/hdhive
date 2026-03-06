# HDHiveSignIn

MoviePilot V2 standalone plugin for HDHive sign-in.

## Repository layout

- `package.v2.json`
- `plugins.v2/hdhivesignin/__init__.py`

## Install

Add this repository to your MoviePilot V2 third-party plugin sources, then install `HDHive 自动签到`.

## Configure

- `站点地址`: default `https://hdhive.com/`
- `Cookie`: full logged-in browser cookie
- `User-Agent`: browser UA matching the cookie
- `定时执行周期`: optional cron
- `立即运行一次`: save once to test

## Notes

The plugin is independent and does not depend on `AutoSignIn`.
