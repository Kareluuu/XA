import os
import requests
from typing import Dict
import time
from datetime import datetime, timedelta
import logging
import json
import hashlib
from pathlib import Path
import streamlit as st

class TwitterCache:
    """Twitter 数据缓存系统"""
    
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_duration = timedelta(minutes=30)  # 缓存30分钟

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        hashed_key = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hashed_key}.json"

    def get(self, key: str) -> Dict:
        """获取缓存数据"""
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            with cache_path.open('r') as f:
                cached_data = json.load(f)
                cache_time = datetime.fromisoformat(cached_data['timestamp'])
                if datetime.now() - cache_time < self.cache_duration:
                    return cached_data['data']
        return None

    def set(self, key: str, data: Dict):
        """设置缓存数据"""
        cache_path = self._get_cache_path(key)
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        with cache_path.open('w') as f:
            json.dump(cache_data, f)

class TwitterAPIv2:
    """Twitter API v2 访问实现"""
    
    def __init__(self):
        self.API_BASE = "https://api.twitter.com/2"
        
        # 尝试多种方式获取凭据
        self.CLIENT_ID = None
        self.CLIENT_SECRET = None
        
        # 1. 首先尝试从环境变量获取
        if os.getenv('TWITTER_CLIENT_ID') and os.getenv('TWITTER_CLIENT_SECRET'):
            self.CLIENT_ID = os.getenv('TWITTER_CLIENT_ID')
            self.CLIENT_SECRET = os.getenv('TWITTER_CLIENT_SECRET')
            st.success("从环境变量加载凭据成功")
            
        # 2. 尝试从Streamlit secrets获取
        if not self.CLIENT_ID:
            try:
                self.CLIENT_ID = st.secrets.get("TWITTER_CLIENT_ID")
                self.CLIENT_SECRET = st.secrets.get("TWITTER_CLIENT_SECRET")
                if self.CLIENT_ID and self.CLIENT_SECRET:
                    st.success("从Streamlit secrets加载凭据成功")
            except Exception as e:
                st.warning(f"从Streamlit secrets加载失败: {str(e)}")
        
        # 3. 如果以上都失败，使用默认值
        if not self.CLIENT_ID:
            self.CLIENT_ID = 'QTRWV3pQSVlBVEVJeXB6RXFmbDI6MTpjaQ'
            self.CLIENT_SECRET = 'sdyzT0lYa5ThsQfSbl5A9Rw1XUfD1lGkQ5ViJivHGdQh45dUv9'
            st.warning("使用默认凭据")
            
            # 显示调试信息
            st.info(f"当前工作目录: {os.getcwd()}")
            st.info(f"secrets.toml位置: {os.path.join(os.getcwd(), '.streamlit', 'secrets.toml')}")
            if os.path.exists(os.path.join(os.getcwd(), '.streamlit', 'secrets.toml')):
                st.info("secrets.toml文件存在")
                with open(os.path.join(os.getcwd(), '.streamlit', 'secrets.toml'), 'r') as f:
                    st.info(f"secrets.toml内容: {f.read()}")
            else:
                st.error("secrets.toml文件不存在")
        
        # 获取Bearer Token
        self.BEARER_TOKEN = self._get_bearer_token()
        
        # 初始化缓存系统
        self.cache = TwitterCache()
        
        # 设置请求头
        self.headers = {
            "Authorization": f"Bearer {self.BEARER_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # 速率限制控制
        self.rate_limit = {
            "remaining": 15,
            "reset_time": datetime.now() + timedelta(minutes=15)
        }
        
        # 设置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _get_bearer_token(self) -> str:
        """获取OAuth 2.0 Bearer Token"""
        # 使用新的Bearer Token
        return "AAAAAAAAAAAAAAAAAAAAANnAxAEAAAAAZPAUnhptfF8XZOqZ4ZSoPgm4PEc%3DQQO7FmG2IjsivpHOORNHIOx9Oyfl7kskEluZWK8OHqTr5Wa9VY"
        
        # 以下是OAuth 2.0的方式，暂时注释掉
        """
        if token := os.getenv('TWITTER_BEARER_TOKEN'):
            return token
            
        auth_url = "https://api.twitter.com/oauth2/token"
        auth_data = {
            'grant_type': 'client_credentials'
        }
        auth_headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # 使用Basic认证
        response = requests.post(
            auth_url,
            auth=(self.CLIENT_ID, self.CLIENT_SECRET),
            data=auth_data,
            headers=auth_headers
        )
        
        if response.status_code == 200:
            return response.json()['access_token']
        else:
            raise ValueError(f"获取Bearer Token失败: {response.text}")
        """

    def get_user_by_username(self, username: str) -> Dict:
        """获取用户信息（带缓存）"""
        cache_key = f"user_{username}"
        cached_data = self.cache.get(cache_key)
        
        if cached_data:
            self.logger.info(f"使用缓存数据: {username}")
            return cached_data
            
        try:
            self._check_rate_limit()
            
            endpoint = f"{self.API_BASE}/users/by/username/{username}"
            params = {
                "user.fields": "created_at,description,location,public_metrics,verified"
            }
            
            self.logger.info(f"请求用户信息: {username}")
            response_data = self._make_request(endpoint, params)
            
            # 缓存结果
            self.cache.set(cache_key, response_data)
            return response_data
            
        except Exception as e:
            self.logger.error(f"获取用户信息失败: {str(e)}")
            raise

    def _check_rate_limit(self):
        """检查并处理速率限制"""
        if self.rate_limit["remaining"] <= 0:
            wait_time = (self.rate_limit["reset_time"] - datetime.now()).total_seconds()
            if wait_time > 0:
                self.logger.info(f"等待速率限制重置，还需 {wait_time:.0f} 秒")
                time.sleep(min(wait_time + 1, 900))  # 最多等待15分钟
                self.rate_limit["remaining"] = 15
                self.rate_limit["reset_time"] = datetime.now() + timedelta(minutes=15)

    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """发送API请求"""
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    endpoint,
                    headers=self.headers,
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.rate_limit["remaining"] -= 1
                    return response.json()
                elif response.status_code == 429:
                    reset_time = response.headers.get("x-rate-limit-reset")
                    if reset_time:
                        self.rate_limit["reset_time"] = datetime.fromtimestamp(int(reset_time))
                    self.rate_limit["remaining"] = 0
                    raise Exception("达到速率限制")
                else:
                    raise Exception(f"API请求失败: {response.status_code}")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    self.logger.info(f"请求失败，{wait_time}秒后重试: {str(e)}")
                    time.sleep(wait_time)
                else:
                    raise

def analyze_twitter_profile(username: str) -> str:
    """主分析函数（带缓存）"""
    api = None  # 初始化api变量
    try:
        api = TwitterAPIv2()
        
        # 尝试获取用户数据
        user_data = api.get_user_by_username(username)
        
        if 'data' not in user_data:
            return "未找到用户数据"
            
        user_info = user_data['data']
        metrics = user_info.get('public_metrics', {})
        
        # 格式化输出
        return f"""
# Twitter 用户分析报告

## 基本信息
- 用户名: @{username}
- 位置: {user_info.get('location', '未知')}
- 认证状态: {'已认证' if user_info.get('verified', False) else '未认证'}

## 社交指标
- 粉丝数: {metrics.get('followers_count', 0):,}
- 关注数: {metrics.get('following_count', 0):,}
- 推文数: {metrics.get('tweet_count', 0):,}

## 账号描述
{user_info.get('description', '无描述')}

## 数据来源
{'使用缓存数据' if api.cache.get(f"user_{username}") else '实时API数据'}
"""

    except Exception as e:
        reset_time = '未知'
        if api and hasattr(api, 'rate_limit'):
            reset_time = api.rate_limit.get('reset_time', '未知')
            
        return f"""
# ⚠️ 访问受限提示

当前状态:
- 错误类型: {type(e).__name__}
- 错误信息: {str(e)}
- API限制重置时间: {reset_time}

建议操作:
1. 等待几分钟后重试
2. 使用缓存数据（如果可用）
3. 检查网络连接
"""
        