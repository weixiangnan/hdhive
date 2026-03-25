import re
import time
import urllib.parse
from random import randint
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.utils.http import RequestUtils


class HostLocSignIn(_PluginBase):
    plugin_name = "HostLoc 自动签到"
    plugin_desc = "独立执行 HostLoc 每天登录和访问别人空间积分任务。"
    plugin_icon = "signin.png"
    plugin_version = "1.0.7"
    plugin_author = "weixiangnan"
    author_url = "https://github.com/weixiangnan"
    plugin_config_prefix = "hostlocsignin_"
    plugin_order = 0
    auth_level = 2

    _enabled: bool = False
    _onlyonce: bool = False
    _notify: bool = False
    _cron: str = ""
    _run_hour: int = 8
    _run_minute: int = 0
    _custom_cron: str = ""
    _cookie: str = ""
    _username: str = ""
    _password: str = ""
    _ua: str = ""
    _proxy: bool = False
    _timeout: int = 20
    _site_url: str = "https://hostloc.com/"
    _visit_count: int = 10
    _space_urls_text: str = ""
    _scheduler: Optional[BackgroundScheduler] = None

    _daily_login_rid = 15
    _visit_space_rid = 16
    _credit_log_url = "home.php?mod=spacecp&ac=credit&op=log&suboperation=creditrulelog"
    _credit_base_url = "home.php?mod=spacecp&ac=credit&op=base"
    _space_fallback_span = 60
    _extra_discovery_paths = [
        "",
        "forum.php?mod=guide&view=new",
        "forum.php",
        "misc.php?mod=ranklist",
    ]

    def init_plugin(self, config: dict = None):
        self.stop_service()

        if config:
            self._enabled = bool(config.get("enabled"))
            self._onlyonce = bool(config.get("onlyonce"))
            self._notify = bool(config.get("notify"))
            self._run_hour = int(config.get("run_hour") or 8)
            self._run_minute = int(config.get("run_minute") or 0)
            self._custom_cron = (config.get("custom_cron") or "").strip()
            legacy_cron = (config.get("cron") or "").strip()
            self._cookie = (config.get("cookie") or "").strip()
            self._username = (config.get("username") or "").strip()
            self._password = (config.get("password") or "").strip()
            self._ua = (config.get("ua") or "").strip()
            self._proxy = bool(config.get("proxy"))
            self._site_url = (config.get("site_url") or "https://hostloc.com/").strip()
            self._timeout = int(config.get("timeout") or 20)
            self._visit_count = min(max(int(config.get("visit_count") or 10), 1), 10)
            self._space_urls_text = (config.get("space_urls") or "").strip()
            self._load_schedule_config(legacy_cron=legacy_cron)

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.sign_in,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="HostLoc 自动签到",
            )
            self._onlyonce = False
            self.__update_config()
            if self._scheduler.get_jobs():
                self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    def __update_config(self):
        self._cron = self.__build_cron()
        self.update_config(
            {
                "enabled": self._enabled,
                "onlyonce": self._onlyonce,
                "notify": self._notify,
                "cron": self._cron,
                "run_hour": self._run_hour,
                "run_minute": self._run_minute,
                "custom_cron": self._custom_cron,
                "cookie": self._cookie,
                "username": self._username,
                "password": self._password,
                "ua": self._ua,
                "proxy": self._proxy,
                "timeout": self._timeout,
                "site_url": self._site_url,
                "visit_count": self._visit_count,
                "space_urls": self._space_urls_text,
            }
        )

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/hostloc_signin",
            "event": EventType.PluginAction,
            "desc": "执行 HostLoc 积分签到",
            "category": "站点",
            "data": {
                "action": "hostloc_signin"
            }
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        self._cron = self.__build_cron()
        if self._enabled and self._cron:
            try:
                return [{
                    "id": "HostLocSignIn",
                    "name": "HostLoc 自动签到",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.sign_in,
                    "kwargs": {}
                }]
            except Exception as err:
                logger.error(f"HostLoc 自动签到定时任务配置错误：{str(err)}")
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "username",
                                        "label": "用户名(可选)",
                                        "placeholder": "填入后可在 Cookie 缺失或失效时自动登录"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "password",
                                        "label": "密码(可选)",
                                        "type": "password",
                                        "placeholder": "填入后可在 Cookie 缺失或失效时自动登录"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "enabled",
                                        "label": "启用插件"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "onlyonce",
                                        "label": "立即运行一次"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "notify",
                                        "label": "发送通知"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "site_url",
                                        "label": "站点地址",
                                        "placeholder": "https://hostloc.com/"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "timeout",
                                        "label": "超时秒数",
                                        "type": "number",
                                        "placeholder": "20"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSelect",
                                    "props": {
                                        "model": "visit_count",
                                        "label": "访问空间次数",
                                        "items": [
                                            {"title": "1", "value": 1},
                                            {"title": "2", "value": 2},
                                            {"title": "3", "value": 3},
                                            {"title": "4", "value": 4},
                                            {"title": "5", "value": 5},
                                            {"title": "6", "value": 6},
                                            {"title": "7", "value": 7},
                                            {"title": "8", "value": 8},
                                            {"title": "9", "value": 9},
                                            {"title": "10", "value": 10}
                                        ]
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSelect",
                                    "props": {
                                        "model": "run_hour",
                                        "label": "每日执行小时",
                                        "items": [
                                            {"title": "00", "value": 0},
                                            {"title": "01", "value": 1},
                                            {"title": "02", "value": 2},
                                            {"title": "03", "value": 3},
                                            {"title": "04", "value": 4},
                                            {"title": "05", "value": 5},
                                            {"title": "06", "value": 6},
                                            {"title": "07", "value": 7},
                                            {"title": "08", "value": 8},
                                            {"title": "09", "value": 9},
                                            {"title": "10", "value": 10},
                                            {"title": "11", "value": 11},
                                            {"title": "12", "value": 12},
                                            {"title": "13", "value": 13},
                                            {"title": "14", "value": 14},
                                            {"title": "15", "value": 15},
                                            {"title": "16", "value": 16},
                                            {"title": "17", "value": 17},
                                            {"title": "18", "value": 18},
                                            {"title": "19", "value": 19},
                                            {"title": "20", "value": 20},
                                            {"title": "21", "value": 21},
                                            {"title": "22", "value": 22},
                                            {"title": "23", "value": 23}
                                        ]
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSelect",
                                    "props": {
                                        "model": "run_minute",
                                        "label": "每日执行分钟",
                                        "items": [
                                            {"title": "00", "value": 0},
                                            {"title": "05", "value": 5},
                                            {"title": "10", "value": 10},
                                            {"title": "15", "value": 15},
                                            {"title": "20", "value": 20},
                                            {"title": "25", "value": 25},
                                            {"title": "30", "value": 30},
                                            {"title": "35", "value": 35},
                                            {"title": "40", "value": 40},
                                            {"title": "45", "value": 45},
                                            {"title": "50", "value": 50},
                                            {"title": "55", "value": 55}
                                        ]
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "proxy",
                                        "label": "使用代理"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "custom_cron",
                                        "label": "高级 cron 覆盖",
                                        "placeholder": "留空则按上方每日时间生成，例如 0 8 * * *"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "space_urls",
                                        "label": "自定义空间链接(可选)",
                                        "rows": 4,
                                        "placeholder": "一行一个 https://hostloc.com/space-username-xxx.html；留空则自动从首页/导读页提取"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "cookie",
                                        "label": "Cookie",
                                        "rows": 6,
                                        "placeholder": "粘贴浏览器中 HostLoc 登录后的完整 Cookie；留空时可尝试用户名/密码自动登录"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "ua",
                                        "label": "User-Agent",
                                        "rows": 3,
                                        "placeholder": "粘贴与 Cookie 对应浏览器的 User-Agent"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VAlert",
                                    "props": {
                                        "type": "info",
                                        "variant": "tonal",
                                        "text": "HostLoc 当前按“每天登录 + 访问别人空间”累计积分。插件会先打开首页触发每天登录，再自动访问其他用户空间；如自动提取到的空间链接不足，可在上方手动补充。MoviePilot 插件不能直接读取浏览器现成 Cookie，但如果填写了用户名和密码，会在 Cookie 缺失或失效时自动登录并回填 Cookie。"
                                    }
                                }]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "notify": False,
            "cron": "0 8 * * *",
            "run_hour": 8,
            "run_minute": 0,
            "custom_cron": "",
            "cookie": "",
            "username": "",
            "password": "",
            "ua": "",
            "proxy": False,
            "timeout": 20,
            "site_url": "https://hostloc.com/",
            "visit_count": 10,
            "space_urls": ""
        }

    def get_page(self) -> List[dict]:
        history = self.get_data("history") or []
        text = "\n".join(
            f"{item.get('time')} [{item.get('status')}] {item.get('message')}"
            for item in history[:20]
        ) or "暂无执行记录"
        return [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [{
                            "component": "VTextarea",
                            "props": {
                                "model": "history_text",
                                "label": "最近执行记录",
                                "rows": 20,
                                "readonly": True,
                                "value": text
                            }
                        }]
                    }
                ]
            }
        ]

    @eventmanager.register(EventType.PluginAction)
    def sign_in(self, event: Event = None):
        if event:
            event_data = event.event_data or {}
            if event_data.get("action") != "hostloc_signin":
                return

        ok, message = self.__do_signin()
        if event:
            self.post_message(
                channel=event.event_data.get("channel"),
                title="HostLoc 自动签到",
                text=message,
                userid=event.event_data.get("user"),
            )
        elif self._notify:
            self.post_message(
                title="HostLoc 自动签到",
                text=message,
            )
        return ok, message

    def __do_signin(self) -> Tuple[bool, str]:
        if not self._ua:
            message = "签到失败，未配置 User-Agent"
            logger.error(message)
            self.__save_history(False, message)
            return False, message

        site_url = self._site_url.rstrip("/") + "/"
        home_html, credit_log_before, ensure_message = self.__ensure_cookie(site_url)
        if not home_html or not credit_log_before:
            message = ensure_message or "签到失败，请检查站点连通性"
            logger.error(message)
            self.__save_history(False, message)
            return False, message

        before_score = self.__query_score(site_url)
        daily_login_done_before = self.__parse_rule_count(credit_log_before, self._daily_login_rid) > 0
        visit_done_before = self.__parse_rule_count(credit_log_before, self._visit_space_rid)
        visit_target = min(max(self._visit_count, 1), 10)
        visit_remaining = max(0, visit_target - visit_done_before)

        visited_ok = 0
        attempted = 0
        if visit_remaining > 0:
            candidates = self.__collect_space_urls(site_url=site_url, home_html=home_html)
            if not candidates:
                message = "签到失败，未提取到可访问的用户空间链接"
                logger.error(message)
                self.__save_history(False, message)
                return False, message

            for url in candidates:
                if visited_ok >= visit_remaining:
                    break
                attempted += 1
                if self.__visit_space(url):
                    visited_ok += 1
                    time.sleep(1)

        credit_log_after = self.__get_authenticated_credit_log(site_url)
        after_score = self.__query_score(site_url)
        daily_login_done_after = self.__parse_rule_count(credit_log_after, self._daily_login_rid) > 0
        visit_done_after = self.__parse_rule_count(credit_log_after, self._visit_space_rid)
        visit_added = max(0, visit_done_after - visit_done_before)

        daily_login_text = "每天登录已完成" if daily_login_done_after else "每天登录未确认"
        if visit_remaining <= 0:
            visit_text = f"访问空间已完成({visit_done_before}/{visit_target})"
        else:
            visit_text = f"访问空间新增 {visit_added}/{visit_remaining} 次"

        score_text = ""
        if before_score is not None and after_score is not None:
            delta = after_score - before_score
            delta_text = f"+{delta}" if delta >= 0 else str(delta)
            score_text = f"，积分 {before_score} -> {after_score}（{delta_text}）"

        visit_requirement_met = visit_remaining <= 0 or visit_added >= visit_remaining
        ok = daily_login_done_after and visit_requirement_met
        if ok:
            message = f"{daily_login_text}，{visit_text}{score_text}"
            logger.info(message)
            self.__save_history(True, message)
            return True, message

        daily_login_before_text = "已完成" if daily_login_done_before else "未完成"
        message = f"{daily_login_text}（执行前{daily_login_before_text}），{visit_text}，页面访问成功 {visited_ok} 个，尝试 {attempted} 个空间{score_text}"
        logger.error(message)
        self.__save_history(False, message)
        return False, message

    def __ensure_cookie(self, site_url: str) -> Tuple[str, str, str]:
        if self._cookie:
            credit_html = self.__get_authenticated_credit_log(site_url)
            if credit_html:
                home_html = self.__get_page_source(site_url)
                if home_html:
                    return home_html, credit_html, ""

        if not self._username or not self._password:
            if self._cookie:
                return "", "", "签到失败，Cookie已失效，且未配置用户名/密码自动登录"
            return "", "", "签到失败，未配置 Cookie，且未配置用户名/密码自动登录"

        cookie, message = self.__login_and_get_cookie(site_url)
        if not cookie:
            return "", "", message or "签到失败，自动登录失败"

        self._cookie = cookie
        self.__update_config()
        home_html = self.__get_page_source(site_url)
        credit_html = self.__get_authenticated_credit_log(site_url)
        if not home_html:
            return "", "", "签到失败，自动登录后无法访问站点首页"
        if not credit_html:
            return "", "", "签到失败，自动登录后仍未进入登录状态"
        return home_html, credit_html, "自动登录成功"

    def __get_authenticated_credit_log(self, site_url: str) -> str:
        html = self.__get_page_source(self.__join_url(site_url, self._credit_log_url))
        if self.__is_credit_log_page(html):
            return html
        return ""

    def __login_and_get_cookie(self, site_url: str) -> Tuple[str, str]:
        try:
            login_url = self.__join_url(site_url, "member.php")
            session = requests.Session()
            payload = {
                "mod": "logging",
                "action": "login",
                "loginsubmit": "yes",
                "infloat": "yes",
                "lssubmit": "yes",
                "inajax": "1",
                "fastloginfield": "username",
                "username": self._username,
                "cookietime": str(randint(1234567, 7654321)),
                "password": self._password,
                "quickforward": "yes",
                "handlekey": "ls",
            }
            headers = {
                "User-Agent": self._ua,
                "Referer": site_url,
                "Origin": site_url.rstrip("/"),
                "Content-Type": "application/x-www-form-urlencoded",
            }
            response = session.post(
                login_url,
                data=payload,
                headers=headers,
                timeout=self._timeout,
                proxies=settings.PROXY if self._proxy else None,
            )
            text = response.text or ""
            if response.status_code >= 400:
                return "", f"签到失败，自动登录返回状态码 {response.status_code}"
            if any(token in text for token in ["登录失败", "密码错误", "登录表单"]):
                return "", "签到失败，HostLoc 用户名或密码错误"

            cookie = "; ".join(f"{cookie.name}={cookie.value}" for cookie in session.cookies)
            if not cookie:
                return "", "签到失败，自动登录未获取到 Cookie"
            logger.info("HostLoc 自动登录成功，已回填 Cookie")
            return cookie, "自动登录成功"
        except Exception as err:
            logger.error(f"HostLoc 自动登录失败：{str(err)}")
            return "", f"签到失败，自动登录异常：{str(err)}"

    def __collect_space_urls(self, site_url: str, home_html: str) -> List[str]:
        urls = []
        seen = set()
        own_uid = self.__extract_uid(home_html) or self.__extract_uid_from_cookie()

        def add(url: str):
            if not url:
                return
            normalized = self.__normalize_space_url(site_url, url)
            if not normalized:
                return
            if own_uid and f"space-uid-{own_uid}.html" in normalized:
                return
            if normalized in seen:
                return
            seen.add(normalized)
            urls.append(normalized)

        for line in self._space_urls_text.splitlines():
            add(line.strip())

        for html in [home_html]:
            for url in self.__extract_space_urls(site_url, html):
                add(url)

        for path in self._extra_discovery_paths[1:]:
            html = self.__get_page_source(self.__join_url(site_url, path))
            if not html:
                continue
            for url in self.__extract_space_urls(site_url, html):
                add(url)
            if len(urls) >= self._visit_count + 5:
                break

        if own_uid:
            try:
                uid = int(own_uid)
                for offset in range(1, self._space_fallback_span + 1):
                    add(f"{site_url}space-uid-{uid + offset}.html")
                    if uid - offset > 0:
                        add(f"{site_url}space-uid-{uid - offset}.html")
                    if len(urls) >= self._visit_count * 3:
                        break
            except Exception:
                pass

        return urls

    def __visit_space(self, url: str) -> bool:
        html = self.__get_page_source(url)
        if not html or self.__is_login_page(html):
            return False
        if any(marker in html for marker in ["最近访客", "访问量", "统计信息", "ta的主页", "记录", "好友数"]):
            logger.info(f"HostLoc 访问空间成功：{url}")
            return True
        return False

    def __query_score(self, site_url: str) -> Optional[int]:
        html = self.__get_page_source(self.__join_url(site_url, self._credit_base_url))
        if not html:
            return None
        matched = re.search(r"积分[:：]\s*</em>\s*(\d+)", html)
        if matched:
            return int(matched.group(1))
        matched = re.search(r"积分[:：]\s*(\d+)", html)
        if matched:
            return int(matched.group(1))
        return None

    @staticmethod
    def __parse_rule_count(html: str, rid: int) -> int:
        if not html:
            return 0
        matched = re.search(
            rf'rid={rid}[^>]*>.*?</a></td>\s*<td>\d+</td>\s*<td>(\d+)</td>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if matched:
            return int(matched.group(1))
        return 0

    @staticmethod
    def __extract_uid(html: str) -> Optional[str]:
        matched = re.search(r"space-uid-(\d+)\.html", html or "")
        return matched.group(1) if matched else None

    def __extract_uid_from_cookie(self) -> Optional[str]:
        cookie = self._cookie or ""
        for pattern in [
            r"_st_t=(\d+)\|",
            r"_lastcheckfeed=(\d+)%7C",
            r"_lastcheckfeed=(\d+)\|",
        ]:
            matched = re.search(pattern, cookie)
            if matched:
                return matched.group(1)
        return None

    @staticmethod
    def __extract_space_urls(site_url: str, html: str) -> List[str]:
        patterns = re.findall(r'href="([^"]*(?:space-uid-\d+|space-username-[^"]+)\.html)"', html or "")
        urls = []
        seen = set()
        for url in patterns:
            absolute = urllib.parse.urljoin(site_url, url)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)
        return urls

    @staticmethod
    def __normalize_space_url(site_url: str, url: str) -> Optional[str]:
        if not url:
            return None
        normalized = urllib.parse.urljoin(site_url, url.strip())
        if "space-uid-" not in normalized and "space-username-" not in normalized:
            return None
        return normalized

    def __get_page_source(self, url: str) -> str:
        try:
            res = RequestUtils(
                cookies=self._cookie,
                ua=self._ua,
                proxies=settings.PROXY if self._proxy else None,
                timeout=self._timeout,
            ).get_res(url=url)
            if not res:
                return ""
            return res.text or ""
        except Exception as err:
            logger.error(f"HostLoc 请求页面失败：{url}，原因：{str(err)}")
            return ""

    @classmethod
    def __is_login_page(cls, text: str) -> bool:
        if cls.__is_logged_in(text):
            return False
        lowered = (text or "").lower()
        return any(marker in lowered for marker in [
            "登录后才可以",
            "欢迎您回来",
            "name=\"loginfield\"",
            "id=\"lsform\"",
        ])

    @staticmethod
    def __is_logged_in(text: str) -> bool:
        content = text or ""
        return any(marker in content for marker in [
            "访问我的空间",
            "退出</a>",
            "积分:",
            "home.php?mod=spacecp",
            "member.php?mod=logging&action=logout",
        ])

    @staticmethod
    def __is_credit_log_page(text: str) -> bool:
        content = text or ""
        return all(marker in content for marker in [
            "系统奖励",
            "访问别人空间",
            "每天登录",
        ])

    @staticmethod
    def __join_url(site_url: str, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return site_url.rstrip("/") + "/" + path.lstrip("/")

    def __save_history(self, success: bool, message: str):
        history = self.get_data("history") or []
        history.insert(0, {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "status": "SUCCESS" if success else "FAIL",
            "message": message,
        })
        self.save_data("history", history[:20])

    def _load_schedule_config(self, legacy_cron: str = ""):
        if self._custom_cron:
            self._cron = self._custom_cron
            return
        if legacy_cron and not self._custom_cron:
            parts = legacy_cron.split()
            if len(parts) == 5 and parts[2:] == ["*", "*", "*"] and parts[0].isdigit() and parts[1].isdigit():
                self._run_minute = int(parts[0])
                self._run_hour = int(parts[1])
            elif legacy_cron:
                self._custom_cron = legacy_cron
                self._cron = legacy_cron
                return
        self._cron = self.__build_cron()

    def __build_cron(self) -> str:
        if self._custom_cron:
            return self._custom_cron
        hour = min(max(int(self._run_hour), 0), 23)
        minute = min(max(int(self._run_minute), 0), 59)
        return f"{minute} {hour} * * *"

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as err:
            logger.error(f"停止 HostLoc 自动签到服务失败：{str(err)}")
