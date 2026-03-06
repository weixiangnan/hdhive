import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.utils.http import RequestUtils


class HDHiveSignIn(_PluginBase):
    plugin_name = "HDHive 自动签到"
    plugin_desc = "独立执行 HDHive 站点签到。"
    plugin_icon = "signin.png"
    plugin_version = "1.0.0"
    plugin_author = "weixiangnan"
    author_url = "https://github.com/weixiangnan"
    plugin_config_prefix = "hdhivesignin_"
    plugin_order = 0
    auth_level = 2

    _enabled: bool = False
    _onlyonce: bool = False
    _notify: bool = False
    _cron: str = ""
    _cookie: str = ""
    _ua: str = ""
    _proxy: bool = False
    _timeout: int = 20
    _site_url: str = "https://hdhive.com/"
    _scheduler: Optional[BackgroundScheduler] = None

    _repeat_regex = [
        r"今天已经签到",
        r"请不要重复签到",
        r"今日已签到",
    ]
    _success_regex = [
        r"签到成功",
        r"本次签到获得",
        r"此次签到您获得",
        r"获得了?\d+.*?(魔力|积分|bonus|上传量)",
    ]

    def init_plugin(self, config: dict = None):
        self.stop_service()

        if config:
            self._enabled = bool(config.get("enabled"))
            self._onlyonce = bool(config.get("onlyonce"))
            self._notify = bool(config.get("notify"))
            self._cron = config.get("cron") or ""
            self._cookie = (config.get("cookie") or "").strip()
            self._ua = (config.get("ua") or "").strip()
            self._proxy = bool(config.get("proxy"))
            self._site_url = (config.get("site_url") or "https://hdhive.com/").strip()
            self._timeout = int(config.get("timeout") or 20)

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.sign_in,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="HDHive 自动签到",
            )
            self._onlyonce = False
            self.__update_config()
            if self._scheduler.get_jobs():
                self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    def __update_config(self):
        self.update_config(
            {
                "enabled": self._enabled,
                "onlyonce": self._onlyonce,
                "notify": self._notify,
                "cron": self._cron,
                "cookie": self._cookie,
                "ua": self._ua,
                "proxy": self._proxy,
                "timeout": self._timeout,
                "site_url": self._site_url,
            }
        )

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/hdhive_signin",
            "event": EventType.PluginAction,
            "desc": "执行 HDHive 签到",
            "category": "站点",
            "data": {
                "action": "hdhive_signin"
            }
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            try:
                return [{
                    "id": "HDHiveSignIn",
                    "name": "HDHive 自动签到",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.sign_in,
                    "kwargs": {}
                }]
            except Exception as err:
                logger.error(f"HDHive 自动签到定时任务配置错误：{str(err)}")
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
                                        "placeholder": "https://hdhive.com/"
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
                                "props": {"cols": 12, "md": 8},
                                "content": [{
                                    "component": "VCronField",
                                    "props": {
                                        "model": "cron",
                                        "label": "定时执行周期",
                                        "placeholder": "5位 cron 表达式，留空则仅手动执行"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "proxy",
                                        "label": "使用代理"
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
                                        "placeholder": "粘贴浏览器中 HDHive 登录后的完整 Cookie"
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
                                        "text": "这是独立插件，不依赖 AutoSignIn。建议先填 Cookie 和 User-Agent，再打开立即运行一次验证。"
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
            "cron": "",
            "cookie": "",
            "ua": "",
            "proxy": False,
            "timeout": 20,
            "site_url": "https://hdhive.com/"
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
            if event_data.get("action") != "hdhive_signin":
                return

        ok, message = self.__do_signin()
        if event:
            self.post_message(
                channel=event.event_data.get("channel"),
                title="HDHive 自动签到",
                text=message,
                userid=event.event_data.get("user"),
            )
        elif self._notify:
            self.post_message(
                title="HDHive 自动签到",
                text=message,
            )
        return ok, message

    def __do_signin(self) -> Tuple[bool, str]:
        if not self._cookie:
            message = "签到失败，未配置 Cookie"
            logger.error(message)
            self.__save_history(False, message)
            return False, message

        if not self._ua:
            message = "签到失败，未配置 User-Agent"
            logger.error(message)
            self.__save_history(False, message)
            return False, message

        site_url = self._site_url.rstrip("/") + "/"
        home_html = self.__get_page_source(site_url)
        if not home_html:
            message = "签到失败，请检查站点连通性"
            logger.error(message)
            self.__save_history(False, message)
            return False, message

        if "login.php" in home_html or "name=\"username\"" in home_html:
            message = "签到失败，Cookie已失效"
            logger.error(message)
            self.__save_history(False, message)
            return False, message

        if self.__match_regex(home_html, self._repeat_regex):
            message = "今日已签到"
            logger.info(message)
            self.__save_history(True, message)
            return True, message

        candidates = [
            ("post", f"{site_url}signin.php", {"action": "post", "content": ""}),
            ("post", f"{site_url}sign_in.php", {"action": "sign_in"}),
            ("get", f"{site_url}attendance.php", None),
            ("get", f"{site_url}plugin_sign-in.php?cmd=signin", None),
        ]
        last_detail = ""
        for method, url, data in candidates:
            ok, message = self.__try_sign(url=url, method=method, data=data)
            if ok:
                self.__save_history(True, message)
                return True, message
            if message == "签到失败，Cookie已失效":
                self.__save_history(False, message)
                return False, message
            if message:
                last_detail = message

        message = "签到失败，未识别可用签到接口"
        if last_detail:
            message = f"{message}：{last_detail}"
        logger.error(message)
        self.__save_history(False, message)
        return False, message

    def __try_sign(self, url: str, method: str, data: Optional[Dict]) -> Tuple[bool, str]:
        try:
            req = RequestUtils(
                cookies=self._cookie,
                ua=self._ua,
                proxies=settings.PROXY if self._proxy else None,
                timeout=self._timeout,
            )
            if method == "post":
                res = req.post_res(url=url, data=data)
            else:
                res = req.get_res(url=url)

            if not res:
                return False, ""

            text = (res.text or "").strip()
            if not text:
                return False, ""
            if "login.php" in text or "name=\"username\"" in text:
                return False, "签到失败，Cookie已失效"
            if text.startswith("{") and text.endswith("}"):
                try:
                    payload = json.loads(text)
                    if self.__json_is_success(payload):
                        logger.info(f"HDHive 签到成功，接口：{url}")
                        return True, "签到成功"
                except Exception:
                    pass
            if self.__match_regex(text, self._repeat_regex):
                logger.info(f"HDHive 今日已签到，接口：{url}")
                return True, "今日已签到"
            if self.__match_regex(text, self._success_regex):
                logger.info(f"HDHive 签到成功，接口：{url}")
                return True, "签到成功"
            return False, text[:120]
        except Exception as err:
            logger.error(f"HDHive 请求签到接口异常：{url}，原因：{str(err)}")
            return False, str(err)

    def __get_page_source(self, url: str) -> str:
        res = RequestUtils(
            cookies=self._cookie,
            ua=self._ua,
            proxies=settings.PROXY if self._proxy else None,
            timeout=self._timeout,
        ).get_res(url=url)
        if not res:
            return ""
        return res.text or ""

    def __save_history(self, success: bool, message: str):
        history = self.get_data("history") or []
        history.insert(0, {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "status": "SUCCESS" if success else "FAIL",
            "message": message,
        })
        self.save_data("history", history[:20])

    @staticmethod
    def __json_is_success(payload: Dict) -> bool:
        for key in ["state", "success", "status", "ok"]:
            if key not in payload:
                continue
            value = payload.get(key)
            if value is True:
                return True
            if isinstance(value, int) and value == 1:
                return True
            if isinstance(value, str) and value.lower() in ["ok", "success", "true", "1"]:
                return True
        return False

    @staticmethod
    def __match_regex(text: str, patterns: List[str]) -> bool:
        normalized = re.sub(r"\s+", "", text or "")
        for pattern in patterns:
            if re.search(pattern, normalized):
                return True
        return False

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as err:
            logger.error(f"停止 HDHive 自动签到服务失败：{str(err)}")
