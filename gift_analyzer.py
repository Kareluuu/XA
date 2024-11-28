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
        self.cache_duration = timedelta(hours=24)  # 增加缓存时间到24小时

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
            "Content-Type": "application/json",
            "User-Agent": "v2UserLookupPython"
        }
        self.rate_limit = {
            "remaining": 25,  # Free Plan每15分钟允许25次请求
            "reset_time": datetime.now() + timedelta(minutes=15),
            "requests_per_window": 25,  # Free Plan限制
            "window_size": 15  # 时间窗口（分钟）
        }
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
            raise ValueError(f"获取Bearer Token失: {response.text}")
        """

    def get_user_by_username(self, username: str) -> Dict:
        """获取用户信息"""
        try:
            self._check_rate_limit()
            
            # 修正：添加具体的endpoint和参数，按照X API文档要求
            endpoint = f"{self.API_BASE}/users/by/username/{username}"
            params = {
                "user.fields": "id,name,username,description,public_metrics,verified,location,created_at",
                "expansions": "pinned_tweet_id"
            }
            
            # 添加错误处理和重试逻辑
            for attempt in range(3):
                try:
                    response = requests.get(
                        endpoint,
                        headers=self.headers,
                        params=params,
                        timeout=10
                    )
                    
                    # 记录响应内容用于调试
                    self.logger.info(f"API Response: {response.status_code}, {response.text}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        # 缓存成功的响应
                        self.cache.set(f"user_{username}", data)
                        return data
                    elif response.status_code == 404:
                        raise Exception("用户不存在")
                    elif response.status_code == 401:
                        raise Exception("认证失败，请检查Token")
                    else:
                        raise Exception(f"API请求失败: {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    if attempt == 2:  # 最后一次尝试
                        raise Exception(f"网络请求失败: {str(e)}")
                    time.sleep(2)  # 重试前等待
                    
        except Exception as e:
            self.logger.error(f"获取用户信息失败: {str(e)}")
            # 尝试从缓存获取
            if cached_data := self.cache.get(f"user_{username}"):
                return cached_data
            raise

    def get_user_tweets(self, user_id: str, max_results: int = 10) -> Dict:
        """获取用户最近7天的推文"""
        try:
            self._check_rate_limit()
            
            endpoint = f"{self.API_BASE}/users/{user_id}/tweets"
            params = {
                "max_results": max_results,
                "tweet.fields": "created_at,text",  # 简化请求字段
                "exclude": "retweets,replies",
                "start_time": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            }
            
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {"data": []}  # 返回空数据而不是抛出异常
            else:
                raise Exception(f"获取推文失败: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"获取推文失败: {str(e)}")
            return {"data": []}  # 出错时返回空数据

    def _check_rate_limit(self):
        """检查并处理速率限制"""
        current_time = datetime.now()
        
        # 如果超过时间窗口，重置限制
        if current_time >= self.rate_limit["reset_time"]:
            self.rate_limit["remaining"] = self.rate_limit["requests_per_window"]
            self.rate_limit["reset_time"] = current_time + timedelta(minutes=self.rate_limit["window_size"])
            
        # 如果剩余请求数不足，直接拒绝
        if self.rate_limit["remaining"] <= 2:  # 保留2个请求额度作为缓冲
            wait_time = (self.rate_limit["reset_time"] - current_time).total_seconds()
            if wait_time > 0:
                minutes = int(wait_time / 60)
                seconds = int(wait_time % 60)
                raise Exception(f"达到速率限制，请等待{minutes}分{seconds}秒")

    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """发API请求"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    endpoint,
                    headers=self.headers,
                    params=params,
                    timeout=10
                )
                
                # 检查响应状态
                if response.status_code == 200:
                    data = response.json()
                    if 'data' in data:
                        return data
                    else:
                        raise Exception("API返回数据格式错误")
                elif response.status_code == 404:
                    raise Exception("用户不存在")
                elif response.status_code == 401:
                    raise Exception("认证失败，请检查Token")
                else:
                    raise Exception(f"API请求失败: {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                raise Exception(f"网络请求失败: {str(e)}")

class GiftAnalyzer:
    """礼物分"""
    
    def __init__(self):
        # 兴趣关键词映射到礼物类别
        self.interest_gift_mapping = {
            "科技": ["智能手表", "无线耳机", "平板电脑", "智能音箱"],
            "游戏": ["游戏机", "游戏周边", "游戏礼品卡", "游戏手柄"],
            "音乐": ["音乐会门票", "蓝牙音箱", "音乐订阅服务", "乐器"],
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
    """主分析函数"""
    api = None
    try:
        api = TwitterAPIv2()
        
        # 验证用户名
        if not username or not username.strip():
            return "# ⚠️ 无效的用户名\n\n请输入有效的Twitter用户名（不需要包含@符号）"
        
        # 移除@符号如果存在
        username = username.strip().lstrip('@')
        
        try:
            # 获取用户信息
            st.info("正在获取用户信息...")
            user_data = api.get_user_by_username(username)
            
            if not user_data or 'data' not in user_data:
                st.error(f"API返回数据: {user_data}")
                return "# ❌ 无效的用户数据\n\n无法获取用户信息，请稍后重试"
                
            user_info = user_data['data']
            user_id = user_info['id']
            
            # 获取最近7天的推文
            st.info("正在获取最近7天的推文...")
            tweets_data = {"data": []}
            
            if api.rate_limit["remaining"] > 1:
                try:
                    tweets_data = api.get_user_tweets(user_id)
                except Exception as e:
                    st.warning(f"获取推文失败: {str(e)}")
            
            # 分析推文
            analyzer = GiftAnalyzer()
            analysis_result = analyzer.analyze_tweets(tweets_data)
            gift_recommendations = analyzer.recommend_gifts(analysis_result)
            
            # 统计推文主题和关键词
            tweet_topics = {}
            keywords = {}
            total_tweets = len(tweets_data.get('data', []))
            
            for tweet in tweets_data.get('data', []):
                text = tweet.get('text', '').lower()
                # 分析主题
                for category, words in analyzer.interest_gift_mapping.items():
                    if any(word.lower() in text for word in words):
                        tweet_topics[category] = tweet_topics.get(category, 0) + 1
                
                # 提取关键词
                words = text.split()
                for word in words:
                    if len(word) > 3:  # 只统计长度大于3的词
                        keywords[word] = keywords.get(word, 0) + 1
            
            # 排序获取最常见的主题和关键词
            top_topics = sorted(tweet_topics.items(), key=lambda x: x[1], reverse=True)[:3]
            top_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:5]
            
            return f"""
# X用户推文分析报告

## 推文分析
- 分析时间范围：最近7天
- 分析推文数量：{total_tweets}条

### 主要话题
{_format_topics(top_topics, total_tweets)}

### 高频关键词
{_format_keywords(top_keywords)}

## 分析结果
{_format_analysis_result(analysis_result)}

## 礼物推荐
基于以上分析，为您推荐以下礼物：
{_format_recommendations(gift_recommendations)}
"""
            
        except Exception as e:
            st.error(f"错误详情: {str(e)}")
            if "用户不存在" in str(e):
                return "# ❌ 用户不存在\n\n该用户名不存在，请检查拼写是否正确"
            elif "认证失败" in str(e):
                return "# ❌ 认证失败\n\n请检查API Token是否有效"
            raise
            
    except Exception as e:
        st.error(f"发生错误: {str(e)}")
        return f"""
# ❌ 分析失败

错误信息: {str(e)}

请确保：
1. 输入的用户名正确
2. 该用户存在且未被限制访问
3. 网络连接正常

建议稍后重试。
"""

def _format_topics(topics: list, total_tweets: int) -> str:
    """格式化主题输出"""
    if not topics:
        return "暂无明显主题"
    
    result = []
    for topic, count in topics:
        percentage = (count / total_tweets * 100) if total_tweets > 0 else 0
        result.append(f"- {topic}: {percentage:.1f}% ({count}条推文)")
    return "\n".join(result)

def _format_keywords(keywords: list) -> str:
    """格式化关键词输出"""
    if not keywords:
        return "暂无高频关键词"
    
    return "\n".join([f"- {word}: 出现{count}次" for word, count in keywords])

def _format_analysis_result(analysis_result: Dict) -> str:
    """格式化分析结果"""
    interests = analysis_result.get('interests', {})
    sentiment = analysis_result.get('sentiment', 0)
    
    result = []
    if interests:
        result.append("用户兴趣倾向：")
        sorted_interests = sorted(interests.items(), key=lambda x: x[1], reverse=True)
        for interest, count in sorted_interests:
            result.append(f"- {interest}")
    else:
        result.append("暂无明显兴趣倾向")
    
    result.append(f"\n情感倾向: {_interpret_sentiment(sentiment)}")
    
    return "\n".join(result)

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
        