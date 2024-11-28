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
        self.cache_duration = timedelta(minutes=0)  # 设置为0以禁用缓存

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
        
        # 2. 尝试从Streamlit secrets获取
        if not self.CLIENT_ID:
            try:
                self.CLIENT_ID = st.secrets.get("TWITTER_CLIENT_ID")
                self.CLIENT_SECRET = st.secrets.get("TWITTER_CLIENT_SECRET")
            except Exception:
                pass
        
        # 3. 如果以上都失败，使用默认值
        if not self.CLIENT_ID:
            self.CLIENT_ID = 'QTRWV3pQSVlBVEVJeXB6RXFmbDI6MTpjaQ'
            self.CLIENT_SECRET = 'sdyzT0lYa5ThsQfSbl5A9Rw1XUfD1lGkQ5ViJivHGdQh45dUv9'
        
        # 获取Bearer Token
        self.BEARER_TOKEN = self._get_bearer_token()
        
        # 初始化其他配置
        self.cache = TwitterCache()
        self.headers = {
            "Authorization": f"Bearer {self.BEARER_TOKEN}",
            "Content-Type": "application/json"
        }
        self.rate_limit = {
            "remaining": 10,  # Free Plan每15分钟10次
            "reset_time": datetime.now() + timedelta(minutes=15),
            "requests_per_window": 10,  # 从50改为10
            "window_size": 15,
            "monthly_limit": 50,  # Free Plan每月限制
            "monthly_used": 0
        }
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # API调用统计
        self.api_stats = {
            "window_start": datetime.now(),
            "calls_in_window": 0,
            "total_calls": 0
        }
        
        # 启动统计打印定时器
        self._start_stats_timer()

    def _start_stats_timer(self):
        """每15分钟打印一次API调用统计"""
        def print_stats():
            while True:
                time.sleep(900)  # 15分钟
                self._print_api_stats()
                # 重置窗口计数
                self.api_stats["window_start"] = datetime.now()
                self.api_stats["calls_in_window"] = 0
        
        # 在后台线程中运行统计
        import threading
        stats_thread = threading.Thread(target=print_stats, daemon=True)
        stats_thread.start()
    
    def _print_api_stats(self):
        """打印API调用统计信息"""
        current_time = datetime.now()
        window_duration = (current_time - self.api_stats["window_start"]).total_seconds() / 60
        
        stats_message = f"""
# 📊 API调用统计 ({current_time.strftime('%Y-%m-%d %H:%M:%S')})

## 当前15分钟窗口
- API调用次数: {self.api_stats["calls_in_window"]}/10
- 剩余可用次数: {self.rate_limit["remaining"]}
- 距离重置: {((self.rate_limit["reset_time"] - current_time).total_seconds() / 60):.1f}分钟
- 平均调用频率: {self.api_stats["calls_in_window"] / window_duration:.2f} 次/分钟

## 累计统计
- 总调用次数: {self.api_stats["total_calls"]}
- 每月限额剩余: {self.rate_limit["monthly_limit"] - self.rate_limit["monthly_used"]}
"""
        st.info(stats_message)

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
            raise ValueError(f"获取Bearer Token失: {response.text}")
        """

    def get_user_by_username(self, username: str) -> Dict:
        """获取用户信息（带缓存）"""
        cache_key = f"user_{username}"
        cached_data = self.cache.get(cache_key)
        
        if cached_data:
            self.logger.info(f"使用缓存数据: {username}")
            return cached_data
            
        # 如果没有缓存且接近限制，直接拒绝
        if self.rate_limit["remaining"] <= 2:  # 为推文请求保留额度
            raise Exception("达到速率限制")
            
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

    def get_user_tweets(self, user_id: str, max_results: int = 5) -> Dict:
        """获取用户最近7天的推文
        Free Plan限制：
        - 每次最多返回100条推文
        - 只能访问最近7天的公开推文
        """
        cache_key = f"tweets_{user_id}"
        cached_data = self.cache.get(cache_key)
        
        if cached_data:
            return cached_data
            
        try:
            self._check_rate_limit()
            
            endpoint = f"{self.API_BASE}/users/{user_id}/tweets"
            params = {
                "max_results": min(max_results, 10),  # 限制每次请求数量
                "tweet.fields": "created_at,public_metrics",
                "exclude": "retweets,replies",
                "start_time": (datetime.now() - timedelta(days=7)).isoformat() + "Z"
            }
            
            self.logger.info(f"请求用户推文: {user_id}")
            response_data = self._make_request(endpoint, params)
            
            # 缓存结果
            self.cache.set(cache_key, response_data)
            return response_data
            
        except Exception as e:
            self.logger.error(f"获取用户推文失败: {str(e)}")
            raise

    def _check_rate_limit(self):
        """检查API限制"""
        current_time = datetime.now()
        
        # 检查15分钟窗口限制
        if current_time >= self.rate_limit["reset_time"]:
            self.rate_limit["remaining"] = self.rate_limit["requests_per_window"]
            self.rate_limit["reset_time"] = current_time + timedelta(minutes=self.rate_limit["window_size"])
        
        # 检查每月限制
        if self.rate_limit["monthly_used"] >= self.rate_limit["monthly_limit"]:
            raise Exception("已达到本月API调用限制")
        
        # 如果剩余请求数不足，拒绝请求
        if self.rate_limit["remaining"] <= 1:  # 保留1个请求作为缓冲
            wait_time = (self.rate_limit["reset_time"] - current_time).total_seconds()
            if wait_time > 0:
                raise Exception("达到速率限制")

    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """发送API请求"""
        try:
            # 先检查速率限制
            self._check_rate_limit()
            
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            # 更新API调用统计
            self.api_stats["calls_in_window"] += 1
            self.api_stats["total_calls"] += 1
            
            # 更新速率限制信息
            if response.status_code == 200:
                self.rate_limit["remaining"] = int(response.headers.get("x-rate-limit-remaining", self.rate_limit["remaining"]))
                reset_time = response.headers.get("x-rate-limit-reset")
                if reset_time:
                    self.rate_limit["reset_time"] = datetime.fromtimestamp(int(reset_time))
                self.rate_limit["monthly_used"] += 1
                return response.json()
            elif response.status_code == 429:  # Rate limit exceeded
                reset_time = response.headers.get("x-rate-limit-reset")
                if reset_time:
                    self.rate_limit["reset_time"] = datetime.fromtimestamp(int(reset_time))
                self.rate_limit["remaining"] = 0
                raise Exception("达到速率限制")
            else:
                raise Exception(f"API请求失败: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求失败: {str(e)}")

class GiftAnalyzer:
    """礼物分"""
    
    def __init__(self):
        # 兴趣关键词映射到礼物类别
        self.interest_gift_mapping = {
            "科技": ["智能手表", "无线耳机", "平板电脑", "智能音箱"],
            "游戏": ["游戏机", "游戏周边", "游戏礼品卡", "游戏手柄"],
            "音乐": ["乐会门票", "蓝牙音箱", "音乐订阅服务", "乐器"],
            "美食": ["美食礼券", "烹饪工具", "精品茶具", "咖啡器具"],
            "运动": ["运动手环", "运动装备", "健身器材", "运动鞋"],
            "读书": ["电子书阅读器", "精装图书", "读书订阅", "书签"],
            "艺术": ["艺术画作", "手工艺品", "相机", "绘画工具"],
            "时尚": ["品牌包包", "饰品", "香水", "时尚配件"]
        }
        
        # 情感词典
        self.sentiment_words = {
            "positive": ["喜欢", "爱", "好", "棒", "赞", "享受", "期待", "感恩"],
            "negative": ["讨厌", "烦", "差", "糟", "失望", "难过", "生气"]
        }

    def analyze_tweets(self, tweets_data: Dict) -> Dict:
        """分析推文内容"""
        if not tweets_data or 'data' not in tweets_data:
            return {"interests": {}, "sentiment": 0}
            
        interests = {}
        sentiment_score = 0
        tweet_count = 0
        
        for tweet in tweets_data['data']:
            # 分析推文文本
            text = tweet.get('text', '').lower()
            tweet_count += 1
            
            # 计算情感分数
            for word in self.sentiment_words["positive"]:
                if word in text:
                    sentiment_score += 1
            for word in self.sentiment_words["negative"]:
                if word in text:
                    sentiment_score -= 1
            
            # 统计兴趣
            for category, keywords in self.interest_gift_mapping.items():
                for keyword in keywords:
                    if keyword in text:
                        interests[category] = interests.get(category, 0) + 1
                        
            # 分析实体标签
            if 'entities' in tweet:
                for entity_type, entities in tweet['entities'].items():
                    for entity in entities:
                        tag = entity.get('tag', '').lower()
                        for category, keywords in self.interest_gift_mapping.items():
                            if any(keyword.lower() in tag for keyword in keywords):
                                interests[category] = interests.get(category, 0) + 1
        
        # 标准化情感分数
        avg_sentiment = sentiment_score / max(tweet_count, 1)
        
        return {
            "interests": interests,
            "sentiment": avg_sentiment
        }

    def recommend_gifts(self, analysis_result: Dict) -> list:
        """基于分析结果推荐礼物"""
        recommendations = []
        
        # 获取最主要的兴趣
        interests = analysis_result["interests"]
        if not interests:
            return ["通用礼品卡", "精美礼品盒", "手工巧克力"]
            
        # 按兴趣频率排序
        sorted_interests = sorted(interests.items(), key=lambda x: x[1], reverse=True)
        
        # 根据前三个主要兴趣推荐礼物
        for category, _ in sorted_interests[:3]:
            recommendations.extend(self.interest_gift_mapping[category][:2])
        
        return recommendations[:5]  # 返回前5个推荐

def analyze_twitter_profile(username: str) -> str:
    """主分析函数（带缓存）"""
    api = None
    try:
        api = TwitterAPIv2()
        
        # 强制优先使用缓存
        cache_key = f"user_{username}"
        user_data = api.cache.get(cache_key)
        
        if user_data:
            st.success("✅ 使用缓存数据进行分析")
            # 如果有缓存数据，直接使用缓存中的推文数据
            user_info = user_data['data']
            user_id = user_info['id']
            metrics = user_info.get('public_metrics', {})
            tweets_cache_key = f"tweets_{user_id}"
            tweets_data = api.cache.get(tweets_cache_key) or {"data": []}
            
        else:
            # 只有在没有缓存且有足够API限额时才请求新数据
            if api.rate_limit["remaining"] <= 1:
                wait_time = (api.rate_limit["reset_time"] - datetime.now()).total_seconds()
                minutes = int(wait_time / 60)
                seconds = int(wait_time % 60)
                return f"""
# ⏳ API访问频率限制

当前状态：已达到API访问限制
预计恢复时间：{minutes}分{seconds}秒后

建议操作：
1. 稍后再试（{minutes}分{seconds}秒后）
2. 尝试分析其他用户（可能有缓存）
"""
            
            user_data = api.get_user_by_username(username)
            user_info = user_data['data']
            user_id = user_info['id']
            metrics = user_info.get('public_metrics', {})
            
            # 只在有足够配额时获取推文
            if api.rate_limit["remaining"] > 1:
                tweets_data = api.get_user_tweets(user_id)
            else:
                tweets_data = {"data": []}
                st.warning("⚠️ 为节省API配额，暂不获取推文数据")
        
        # 分析推文
        analyzer = GiftAnalyzer()
        analysis_result = analyzer.analyze_tweets(tweets_data)
        gift_recommendations = analyzer.recommend_gifts(analysis_result)
        
        # 格式化输出
        return f"""
# Twitter 用户分析报告 {'(缓存数据)' if api.cache.get(cache_key) else ''}

## 基本信息
- 用户名: @{username}
- 位置: {user_info.get('location', '未知')}
- 认证状态: {'已认证' if user_info.get('verified', False) else '未认证'}

## 社交指标
- 粉丝数: {metrics.get('followers_count', 0):,}
- 关注数: {metrics.get('following_count', 0):,}
- 推文数: {metrics.get('tweet_count', 0):,}

## 兴趣分析
{_format_interests(analysis_result['interests'])}

## 情感倾向
情感指数: {analysis_result['sentiment']:.2f}
({_interpret_sentiment(analysis_result['sentiment'])})

## 礼物推荐
{_format_recommendations(gift_recommendations)}

## 账号描述
{user_info.get('description', '无描述')}
"""

    except Exception as e:
        if "达到速率限制" in str(e):
            if api and hasattr(api, 'rate_limit'):
                wait_time = (api.rate_limit["reset_time"] - datetime.now()).total_seconds()
                minutes = int(wait_time / 60)
                seconds = int(wait_time % 60)
                return f"""
# ⏳ API访问频率限制

当前状态：已达到API访问限制
预计恢复时间：{minutes}分{seconds}秒后

建议操作：
1. 稍后再试
2. 尝试分析其他用户
3. 等待 {minutes}分{seconds}秒 后刷新
"""
        
        return """
# ❌ 分析失败

抱歉无法完成分析。请确保：
1. 输入的用户名正确
2. 该用户存在且未被限制访问
3. 网络连接正常

建议稍后重试。
"""

def _format_interests(interests: Dict) -> str:
    """格式化兴趣输出"""
    if not interests:
        return "暂无明显兴趣倾向"
    
    sorted_interests = sorted(interests.items(), key=lambda x: x[1], reverse=True)
    return "\n".join([f"- {category}: {'🌟' * min(count, 5)}" for category, count in sorted_interests])

def _interpret_sentiment(score: float) -> str:
    """解释情感分数"""
    if score > 0.5:
        return "非常积极"
    elif score > 0:
        return "较为积极"
    elif score == 0:
        return "中性"
    elif score > -0.5:
        return "较为消极"
    else:
        return "非常消极"

def _format_recommendations(recommendations: list) -> str:
    """格式化推荐礼物输出"""
    return "\n".join([f"- {gift}" for gift in recommendations])
        