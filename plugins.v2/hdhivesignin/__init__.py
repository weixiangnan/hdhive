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
    plugin_version = "1.10"
    plugin_author = "weixiangnan"
    author_url = "https://github.com/weixiangnan"
    plugin_config_prefix = "hdhivesignin_"
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
    _ua: str = ""
    _proxy: bool = False
    _timeout: int = 20
    _site_url: str = "https://hdhive.com/"
    _sign_path: str = ""
    _sign_method: str = "POST"
    _sign_body: str = ""
    _sign_headers: str = ""
    _success_regex_text: str = ""
    _repeat_regex_text: str = ""
    _scheduler: Optional[BackgroundScheduler] = None

    _repeat_regex = [
        r"今天已经签到",
        r"请不要重复签到",
        r"今日已签到",
        r"你已经签到过了",
        r"明天再来吧",
    ]
    _success_regex = [
        r"签到成功",
        r"本次签到获得",
        r"此次签到您获得",
        r"获得了?\d+.*?(魔力|积分|bonus|上传量)",
        r"\"success\":true",
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
            self._ua = (config.get("ua") or "").strip()
            self._proxy = bool(config.get("proxy"))
            self._site_url = (config.get("site_url") or "https://hdhive.com/").strip()
            self._timeout = int(config.get("timeout") or 20)
            self._sign_path = (config.get("sign_path") or "").strip()
            self._sign_method = (config.get("sign_method") or "POST").strip().upper()
            self._sign_body = (config.get("sign_body") or "").strip()
            self._sign_headers = (config.get("sign_headers") or "").strip()
            self._success_regex_text = (config.get("success_regex") or "").strip()
            self._repeat_regex_text = (config.get("repeat_regex") or "").strip()
            self._load_schedule_config(legacy_cron=legacy_cron)

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
                "ua": self._ua,
                "proxy": self._proxy,
                "timeout": self._timeout,
                "site_url": self._site_url,
                "sign_path": self._sign_path,
                "sign_method": self._sign_method,
                "sign_body": self._sign_body,
                "sign_headers": self._sign_headers,
                "success_regex": self._success_regex_text,
                "repeat_regex": self._repeat_regex_text,
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
        self._cron = self.__build_cron()
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
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "sign_headers",
                                        "label": "自定义请求头(JSON)",
                                        "rows": 4,
                                        "placeholder": "{\"Accept\":\"text/x-component\",\"next-action\":\"...\"}"
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
                                "props": {"cols": 12, "md": 8},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "sign_path",
                                        "label": "自定义签到路径",
                                        "placeholder": "/api/xxx 或完整 https:// 链接；留空则按内置候选尝试"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSelect",
                                    "props": {
                                        "model": "sign_method",
                                        "label": "签到请求方法",
                                        "items": [
                                            {"title": "POST", "value": "POST"},
                                            {"title": "GET", "value": "GET"}
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
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "sign_body",
                                        "label": "自定义请求体(JSON 或 key=value&key2=value2)",
                                        "rows": 3,
                                        "placeholder": "{\"action\":\"checkin\"}"
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
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "success_regex",
                                        "label": "成功关键词/正则",
                                        "rows": 3,
                                        "placeholder": "每行一个，留空使用内置规则"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "repeat_regex",
                                        "label": "已签到关键词/正则",
                                        "rows": 3,
                                        "placeholder": "每行一个，留空使用内置规则"
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
                                        "text": "默认按“每日执行小时/分钟”生成计划，例如 08:00 会生成 0 8 * * *。只有需要复杂计划时才填写高级 cron 覆盖。HDHive 当前签到走前端 Server Action，默认会尝试 POST /tv + [false]；如失败，请把浏览器抓到的 next-action 等请求头填入自定义请求头。"
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
            "ua": "",
            "proxy": False,
            "timeout": 20,
            "site_url": "https://hdhive.com/",
            "sign_path": "",
            "sign_method": "POST",
            "sign_body": "",
            "sign_headers": "",
            "success_regex": "",
            "repeat_regex": ""
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

        if self.__is_login_page(home_html):
            message = "签到失败，Cookie已失效"
            logger.error(message)
            self.__save_history(False, message)
            return False, message

        if self.__match_regex(home_html, self.__repeat_patterns()):
            message = "今日已签到"
            logger.info(message)
            self.__save_history(True, message)
            return True, message

        candidates = []
        if self._sign_path:
            candidates.append((
                self._sign_method.lower(),
                self.__join_url(site_url, self._sign_path),
                self.__parse_sign_body(),
            ))
        else:
            candidates.append((
                "post",
                f"{site_url}tv",
                [False],
            ))
        candidates.extend([
            ("post", f"{site_url}signin.php", {"action": "post", "content": ""}),
            ("post", f"{site_url}sign_in.php", {"action": "sign_in"}),
            ("get", f"{site_url}attendance.php", None),
            ("get", f"{site_url}plugin_sign-in.php?cmd=signin", None),
        ])
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

    def __try_sign(self, url: str, method: str, data: Any) -> Tuple[bool, str]:
        try:
            headers = self.__request_headers()
            req = RequestUtils(
                cookies=self._cookie,
                ua=self._ua,
                headers=headers,
                proxies=settings.PROXY if self._proxy else None,
                timeout=self._timeout,
            )
            if method == "post":
                if isinstance(data, list):
                    res = req.post_res(url=url, data=json.dumps(data))
                else:
                    res = req.post_res(url=url, data=data)
            else:
                res = req.get_res(url=url)

            if not res:
                return False, ""

            text = (res.text or "").strip()
            if not text:
                return False, ""
            if self.__is_login_page(text):
                return False, "签到失败，Cookie已失效"
            server_action_result = self.__parse_server_action_result(text)
            if server_action_result:
                return server_action_result
            if text.startswith("{") and text.endswith("}"):
                try:
                    payload = json.loads(text)
                    if self.__json_is_success(payload):
                        logger.info(f"HDHive 签到成功，接口：{url}")
                        return True, "签到成功"
                except Exception:
                    pass
            if self.__match_regex(text, self.__repeat_patterns()):
                logger.info(f"HDHive 今日已签到，接口：{url}")
                return True, "今日已签到"
            if self.__match_regex(text, self.__success_patterns()):
                logger.info(f"HDHive 签到成功，接口：{url}")
                return True, "签到成功"
            snippet = re.sub(r"\s+", " ", text)[:200]
            return False, f"接口 {url} 返回：{snippet}"
        except Exception as err:
            logger.error(f"HDHive 请求签到接口异常：{url}，原因：{str(err)}")
            return False, str(err)

    def __get_page_source(self, url: str) -> str:
        res = RequestUtils(
            cookies=self._cookie,
            ua=self._ua,
            headers=self.__request_headers(),
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

    def __success_patterns(self) -> List[str]:
        if self._success_regex_text:
            return [line.strip() for line in self._success_regex_text.splitlines() if line.strip()]
        return self._success_regex

    def __repeat_patterns(self) -> List[str]:
        if self._repeat_regex_text:
            return [line.strip() for line in self._repeat_regex_text.splitlines() if line.strip()]
        return self._repeat_regex

    @staticmethod
    def __is_login_page(text: str) -> bool:
        return any(marker in (text or "") for marker in [
            "login.php",
            "name=\"username\"",
            "NEXT_REDIRECT;replace;/login",
            "/login?redirect=",
        ])

    @staticmethod
    def __join_url(site_url: str, sign_path: str) -> str:
        if sign_path.startswith("http://") or sign_path.startswith("https://"):
            return sign_path
        return site_url.rstrip("/") + "/" + sign_path.lstrip("/")

    def __parse_sign_body(self) -> Any:
        if not self._sign_body:
            return None
        if self._sign_body in ["[false]", "[False]"]:
            return [False]
        if self._sign_body.startswith("{") and self._sign_body.endswith("}"):
            try:
                return json.loads(self._sign_body)
            except Exception:
                return None
        if self._sign_body.startswith("[") and self._sign_body.endswith("]"):
            try:
                return json.loads(self._sign_body)
            except Exception:
                return None
        data = {}
        for item in self._sign_body.split("&"):
            if not item or "=" not in item:
                continue
            key, value = item.split("=", 1)
            data[key] = value
        return data or None

    def __request_headers(self) -> Dict[str, str]:
        headers = {}
        if self._sign_headers.startswith("{") and self._sign_headers.endswith("}"):
            try:
                payload = json.loads(self._sign_headers)
                if isinstance(payload, dict):
                    headers.update({str(key): str(value) for key, value in payload.items()})
            except Exception:
                logger.error("HDHive 自定义请求头不是合法 JSON，已忽略")
        return headers

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

    def __parse_server_action_result(self, text: str) -> Optional[Tuple[bool, str]]:
        for line in text.splitlines():
            line = line.strip()
            if not line or ":{" not in line:
                continue
            _, json_part = line.split(":", 1)
            try:
                payload = json.loads(json_part)
            except Exception:
                continue

            error = payload.get("error")
            if isinstance(error, dict):
                description = str(error.get("description") or "")
                message = str(error.get("message") or "")
                code = str(error.get("code") or "")
                merged = f"{message} {description} {code}"
                if self.__looks_like_repeat_message(merged):
                    logger.info("HDHive 今日已签到")
                    return True, "今日已签到"
                if self.__looks_like_success_message(merged):
                    logger.info("HDHive 签到成功")
                    return True, "签到成功"

            if self.__json_is_success(payload):
                logger.info("HDHive 签到成功")
                return True, "签到成功"
        return None

    @staticmethod
    def __looks_like_repeat_message(text: str) -> bool:
        lowered = (text or "").lower()
        return any(token in lowered for token in [
            "已经签到",
            "今日已签到",
            "明天再来",
            "already signed",
            "already checked",
            "code 400",
            "\"code\":\"400\"",
            "success\":false",
            "ç­¾å°å¤±è´¥",
            "ä½ å·²ç»ç­¾å°è¿äº",
        ])

    @staticmethod
    def __looks_like_success_message(text: str) -> bool:
        lowered = (text or "").lower()
        return any(token in lowered for token in [
            "签到成功",
            "sign success",
            "checkin success",
            "\"success\":true",
        ])

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
