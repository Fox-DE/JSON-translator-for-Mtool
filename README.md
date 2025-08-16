# JSON-translator-for-Mtool
A Python script that processes raw game text exported from mtool, translates it using a custom large language model API, and exports it as a standalone translation file compatible with mtool.

使用方法：

依赖安装pip install requests/conda install requests

首先从Mtool导出游戏原文本的json文件，

随后在脚本中修改源文件目录，并在translate_config.json配置大模型api，建议使用兼容openai api，翻译每批次数量即batch_size也可于此修改，以及可修改每隔x步写入中间文件的save_interval，会自动检测是否。提示词于脚本中，可进行针对性修改。
