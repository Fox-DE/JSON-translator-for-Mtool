# JSON-translator-for-Mtool
A Python script that processes raw game text exported from mtool, translates it using a custom large language model API, and exports it as a standalone translation file compatible with mtool.

### 前置依赖

当前程序在python3.12测试通过，除了标准库外仅需要requests库依赖

```python
pip install requests
# 或使用conda
conda install requests
```

### 操作流程
1. **导出原文**

   - 通过Mtool启动游戏
   - 切换至"翻译"选项卡
   - 点击"开始新的翻译"
   - 选择"导出待翻译的原文"，保存为JSON文件

2. **配置参数**
   - 修改脚本中`input_file`路径指向导出的JSON文件
   - 在`translate_config.json`中配置：
     - 大型语言模型API端点（需兼容OpenAI API）与对应的API密钥
     - 批次大小(`batch_size`)（默认为30）
     - 自动保存间隔(`save_interval`)（默认每10个翻译保存一次，在批次大小为30的情况下，即每批翻译完都保存到中间状态）
   - 按需修改脚本中的提示词模板

3. **执行翻译**

   确保python环境/虚拟环境正确后

   ```bash
   python main.py
   ```

4. **导入译文**
   - 将生成的翻译文件放入游戏根目录
   - 在Mtool翻译选项卡点击"加载翻译文件"
   - 选择翻译后的JSON文件
   - 直接导入中间状态的翻译文件也可，翻译文件中未包含的文本会自动使用原文
```markdown
目录内已包含一个测试用翻译文件ManualTransFile，可删除或者替换
```
## 配置建议
| 参数              | 说明                                                         |
| ----------------- | ------------------------------------------------------------ |
| `batch_size`      | 每批次处理条目数，小模型建议调低(5-10)，大模型可提高(15-30)  |
| `save_interval`   | 自动保存进度间隔，防止意外中断                               |
| `enable_thinking` | 针对硅基Qwen3:8b模型的特殊开关，设为`false`避免思考过程干扰翻译结果 |

## 模型兼容性
✅ **推荐方案**  
- DeepSeek-v3（高准确度，低错译率）  
- 其他高参数量大模型 

**免费方案**
- 硅基流动平台Qwen3:8b模型
- Ollama本地运行Qwen3:8b，实测速度高于硅基流动，但是需要自己电脑运行大模型，需要8g显存

⚠️ **注意事项**  
1. 使用硅基流动Qwen3:8b等小模型时：
   - 需修改提示词，小模型对日文的识别远弱于大模型，deepseek-v3会进行翻译的文本Qwen3:8b很有可能不翻译原文输出
   - 降低`batch_size`
   - 启用`enable_thinking=false`参数
2. API服务需完整兼容OpenAI格式
3. 译文生成后建议人工校验关键术语

