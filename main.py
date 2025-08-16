import json
import requests
import time
import os
from typing import Dict, Any, Tuple, Optional
import logging
from datetime import datetime

class JSONTranslator:
    def __init__(self, config_file: str = "translate_config.json"):
        """
        初始化翻译器
        
        Args:
            config_file: 配置文件路径
        """
        self.config = self.load_config(config_file)
        self.setup_logging()
        
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 验证必要的配置项
            required_keys = ['api_endpoint', 'api_key', 'model', 'source_language', 'target_language']
            for key in required_keys:
                if key not in config:
                    raise ValueError(f"配置文件中缺少必要项: {key}")
            
            # 设置默认值
            config.setdefault('max_retries', 3)
            config.setdefault('retry_delay', 5)
            config.setdefault('request_timeout', 60)  # 增加超时时间用于批量请求
            config.setdefault('batch_size', 50)  # 增加批量大小
            config.setdefault('save_interval', 100)
            config.setdefault('api_type', 'openai')  # 默认为openai兼容API
            
            return config
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件 {config_file} 不存在")
        except json.JSONDecodeError:
            raise ValueError(f"配置文件 {config_file} 格式错误")
    
    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('translation.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def translate_batch(self, texts: list) -> dict:
        """
        批量翻译多个文本
        
        Args:
            texts: 要翻译的文本列表，格式为 [(key, value), ...]
            
        Returns:
            翻译结果字典 {key: translated_text}
        """
        if not texts:
            return {}
        
        # 根据API类型设置不同的请求头和URL
        if self.config.get('api_type', 'openai') == 'google':
            headers = {
                'Content-Type': 'application/json'
            }
            api_url = f"{self.config['api_endpoint']}?key={self.config['api_key']}"
        else:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.config["api_key"]}'
            }
            api_url = self.config['api_endpoint']
        
        # 构建批量翻译的提示词，使用特殊分隔符避免换行符混淆
        batch_text = ""
        for i, (key, value) in enumerate(texts):
            # 将换行符转换为可见的标记，避免在批量处理时混淆
            escaped_value = value.replace('\n', '\\n').replace('\t', '\\t')
            batch_text += f"[{i+1}] {escaped_value}\n"
        
        prompt = f"""请按照以下规则批量处理文本：
1. 如果文本包含日文（平假名、片假名、汉字），请翻译为中文
2. 如果文本是纯英文、数字、符号或ID，请保持原样不变
3. 必须保持原文中的所有格式，包括\\n换行符、空格、标点符号等
4. 按照输入的序号顺序返回结果，每行一个结果
5. 只返回处理后的结果，不要添加序号、解释或其他内容
6. 如果原文包含\\n，翻译结果也必须在相应位置包含\\n
7. 如果无法确定如何处理，请保持原文不变

要处理的文本：
{batch_text}"""
        
        data = {
            'model': self.config['model'],
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'max_tokens': 4000,  # 增加token限制用于批量翻译
            'temperature': 0.3
        }
        
        for attempt in range(self.config['max_retries']):
            try:
                response = requests.post(
                    api_url,
                    headers=headers,
                    json=data,
                    timeout=self.config['request_timeout']
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        translation_text = result['choices'][0]['message']['content'].strip()
                        
                        # 解析批量翻译结果
                        translated_results = {}
                        translation_lines = translation_text.split('\n')
                        
                        for i, (key, original_value) in enumerate(texts):
                            if i < len(translation_lines):
                                translated_line = translation_lines[i].strip()
                                # 移除可能的序号前缀
                                import re
                                translated_line = re.sub(r'^\[\d+\]\s*', '', translated_line)
                                # 恢复换行符和制表符
                                translated_line = translated_line.replace('\\n', '\n').replace('\\t', '\t')
                                
                                if self.is_valid_translation(original_value, translated_line):
                                    translated_results[key] = translated_line
                                    self.logger.info(f"批量翻译成功: {original_value[:20]}... -> {translated_line[:20]}...")
                                else:
                                    translated_results[key] = original_value
                                    self.logger.warning(f"批量翻译结果无效，保留原文: {original_value[:20]}...")
                            else:
                                # 如果翻译结果行数不够，保留原文
                                translated_results[key] = original_value
                                self.logger.warning(f"批量翻译结果行数不足，保留原文: {key}")
                        
                        return translated_results
                    else:
                        self.logger.error(f"API响应格式错误: {result}")
                        
                elif response.status_code == 429:  # 达到限额
                    self.logger.warning(f"API限额达到，等待 {self.config['retry_delay']} 秒后重试...")
                    time.sleep(self.config['retry_delay'])
                    
                elif response.status_code == 401:  # API密钥错误
                    self.logger.error("API密钥错误，请检查配置")
                    return {}
                    
                else:
                    self.logger.error(f"批量翻译API请求失败，状态码: {response.status_code}, 响应: {response.text}")
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"批量翻译请求超时，第 {attempt + 1} 次尝试...")
                
            except requests.exceptions.ConnectionError:
                self.logger.warning(f"批量翻译连接失败，第 {attempt + 1} 次尝试...")
                
            except Exception as e:
                self.logger.error(f"批量翻译过程中出现错误: {str(e)}")
                
            if attempt < self.config['max_retries'] - 1:
                time.sleep(self.config['retry_delay'])
        
        # 如果批量翻译失败，返回原文
        return {key: value for key, value in texts}
    
    def clean_translation_result(self, text: str) -> str:
        """
        清理翻译结果，移除思考标签和多余内容
        
        Args:
            text: 原始翻译结果
            
        Returns:
            清理后的翻译结果
        """
        import re
        
        # 移除 <think> 标签及其内容（包括不完整的标签）
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)  # 移除不完整的开始标签
        text = re.sub(r'.*</think>', '', text, flags=re.DOTALL)  # 移除不完整的结束标签
        
        # # 移除常见的无关内容和残留片段
        # unwanted_patterns = [
        #     r'/无思考', r'/无.*?考', r'/ no_t.*?', r'/no_th.*?', r'/no_think',
        #     r'根据规则.*?', r'按照.*?规则.*?', r'文本内容.*?',
        #     r'处理结果.*?', r'翻译结果.*?', r'hink.*?', r'ink.*?', r'nk.*?'
        # ]
        
        # for pattern in unwanted_patterns:
        #     text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # # 移除单独的think相关词汇
        # text = re.sub(r'\bthink\b', '', text, flags=re.IGNORECASE)
        # text = re.sub(r'\bink\b', '', text, flags=re.IGNORECASE)
        # text = re.sub(r'\bnk\b', '', text, flags=re.IGNORECASE)
        
        # 清理多余的空白字符和换行
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def is_valid_translation(self, original: str, translation: str) -> bool:
        """
        验证翻译结果是否有效
        
        Args:
            original: 原文
            translation: 翻译结果
            
        Returns:
            翻译是否有效
        """
        if not translation or not translation.strip():
            print(f"翻译结果为空或仅包含空白字符")
            return False
        
        # 去除空白字符进行比较
        original_clean = original.strip()
        translation_clean = translation.strip()
        
        # 检查翻译结果是否包含明显的错误信息
        error_patterns = [
            'translation failed', '翻译失败', '无法翻译', '错误', 
            'sorry', 'i cannot', 'i can\'t', 'unable to', 'error occurred',
            'something went wrong', '出现错误', '无法处理'
        ]
        
        translation_lower = translation_clean.lower()
        for pattern in error_patterns:
            if pattern in translation_lower:
                print(f"翻译结果包含错误信息")
                return False
        
        # 检查翻译结果长度是否过长（可能是错误或包含解释）
        if len(translation_clean) > len(original_clean) * 5:  # 允许更大的长度差异
            print(f"翻译结果长度异常")
            return False
        
        # 其他情况都认为是有效的
        return True
    
    def save_progress(self, translated_data: Dict[str, str], progress_file: str):
        """保存翻译进度"""
        try:
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(translated_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"翻译进度已保存到: {progress_file}")
        except Exception as e:
            self.logger.error(f"保存进度失败: {str(e)}")
    
    def load_progress(self, progress_file: str) -> Dict[str, str]:
        """加载翻译进度"""
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.logger.info(f"从 {progress_file} 加载了 {len(data)} 条翻译记录")
                return data
            except Exception as e:
                self.logger.error(f"加载进度失败: {str(e)}")
                return {}
        return {}
    
    def should_translate(self, key: str, value: str) -> bool:
        """
        判断是否需要翻译 - 现在对所有非空文本都进行处理
        
        Args:
            key: JSON键
            value: JSON值
            
        Returns:
            是否需要翻译
        """
        # 只跳过空字符串
        if not value or not value.strip():
            return False
            
        # 对所有其他文本都进行处理，让AI来判断是否需要翻译
        return True
    
    def translate_json_file(self, 
                          input_file: str, 
                          output_file: str, 
                          progress_file: str = None) -> bool:
        """
        翻译JSON文件 - 使用批量翻译提高效率
        
        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            progress_file: 进度文件路径
            
        Returns:
            翻译是否成功完成
        """
        if not progress_file:
            progress_file = f"{input_file}.progress.json"
        
        try:
            # 加载原始数据
            with open(input_file, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
            
            self.logger.info(f"加载了 {len(original_data)} 条记录")
            
            # 加载进度（如果存在）
            translated_data = self.load_progress(progress_file)
            
            # 统计信息
            total_items = len(original_data)
            completed_items = len(translated_data)
            
            self.logger.info(f"总计: {total_items} 条，已完成: {completed_items} 条")
            
            # 收集需要翻译的项目
            items_to_translate = []
            for key, value in original_data.items():
                # 跳过已翻译的项目
                if key in translated_data:
                    continue
                
                # 判断是否需要翻译
                if not self.should_translate(key, value):
                    translated_data[key] = value
                    continue
                
                items_to_translate.append((key, value))
            
            self.logger.info(f"需要翻译的项目: {len(items_to_translate)} 条")
            
            # 批量翻译
            batch_size = self.config['batch_size']
            failed_batches = 0
            
            for i in range(0, len(items_to_translate), batch_size):
                batch = items_to_translate[i:i + batch_size]
                self.logger.info(f"正在处理批次 {i//batch_size + 1}/{(len(items_to_translate) + batch_size - 1)//batch_size}，包含 {len(batch)} 个项目")
                
                # 批量翻译这一批次
                batch_results = self.translate_batch(batch)
                
                if batch_results:
                    # 更新翻译结果
                    translated_data.update(batch_results)
                    failed_batches = 0  # 重置失败计数
                    self.logger.info(f"批次翻译成功，已完成 {len(translated_data)}/{total_items} 条记录")
                else:
                    # 批量翻译失败，尝试更小的批次
                    self.logger.warning("批量翻译失败，尝试更小的批次")
                    failed_batches += 1
                    
                    # 将批次拆分为更小的单位重试
                    for key, value in batch:
                        # 即使是单个元素也使用批量翻译接口
                        single_batch_result = self.translate_batch([(key, value)])
                        if single_batch_result and key in single_batch_result:
                            translated_data[key] = single_batch_result[key]
                            self.logger.info(f"单元素批量翻译成功: {key}")
                        else:
                            # 翻译失败，保留原文
                            translated_data[key] = value
                            self.logger.error(f"翻译失败，保留原文: {key}")
                        
                        # 避免请求过快
                        time.sleep(0.5)
                    
                    # 如果连续多个批次失败，可能是API问题
                    if failed_batches >= 5:
                        self.logger.error("连续批量翻译失败次数过多，保存当前进度并停止")
                        self.save_progress(translated_data, progress_file)
                        return False
                
                # 定期保存进度
                if (i // batch_size + 1) % (self.config['save_interval'] // batch_size + 1) == 0:
                    self.save_progress(translated_data, progress_file)
                
                # 避免请求过快，批量翻译间隔稍长
                time.sleep(1.0)
            
            # 保存最终结果
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(translated_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"翻译完成！结果已保存到: {output_file}")
            
            # 删除进度文件
            if os.path.exists(progress_file):
                os.remove(progress_file)
                self.logger.info("进度文件已删除")
            
            return True
            
        except FileNotFoundError:
            self.logger.error(f"输入文件不存在: {input_file}")
            return False
        except json.JSONDecodeError:
            self.logger.error(f"输入文件格式错误: {input_file}")
            return False
        except Exception as e:
            self.logger.error(f"翻译过程中出现错误: {str(e)}")
            return False

def main():
    """主函数"""
    print("JSON文件自动翻译工具")
    print("=" * 50)
    
    # 创建翻译器实例
    try:
        translator = JSONTranslator()
    except Exception as e:
        print(f"初始化翻译器失败: {e}")
        return
    
    # 设置文件路径
    input_file = "ManualTransFile.json"
    output_file = f"translated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    progress_file = "translation_progress.json"
    
    print(f"输入文件: {input_file}")
    print(f"输出文件: {output_file}")
    print(f"进度文件: {progress_file}")
    print()
    
    # 检查是否存在进度文件
    if os.path.exists(progress_file):
        response = input("发现翻译进度文件，是否继续之前的翻译？(y/n): ")
        if response.lower() not in ['y', 'yes', '是']:
            os.remove(progress_file)
            print("已删除进度文件，将重新开始翻译")
    
    print("开始翻译...")
    success = translator.translate_json_file(input_file, output_file, progress_file)
    
    if success:
        print("翻译成功完成！")
    else:
        print("翻译中断，可稍后继续")

if __name__ == "__main__":
    main()
