<p align="center">
  <img src='figures/icon.png' width='100' hight='100' style="vertical-align: middle;">
</p>

<h1 align="center">EcoAgent (AAAI 2026)</h1>
<h2 align="center">An Efficient Device-Cloud Collaborative Multi-Agent Framework for Mobile Automation</h2>

<p align="center">
  <!-- Arxiv -->
  <a href="https://arxiv.org/abs/2505.05440">
    <img src="https://img.shields.io/badge/arXiv-Paper-B31B1B.svg?style=for-the-badge&logo=arxiv">
  </a>
  <!-- License -->
  <a href="https://github.com/Yi-Biao/EcoAgent/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge">
  </a>
  <!-- Python -->
  <img src="https://img.shields.io/badge/Python-3.12+-green.svg?style=for-the-badge&logo=python">
</p>




EcoAgent is a **privacy-aware, efficient, and responsive** multi-agent framework designed for **Android mobile automation**. Unlike traditional cloud-only mobile agents, EcoAgent introduces a **closed-loop device–cloud collaboration** mechanism that reduces cost, latency, and data transmission while maintaining high automation performance.

<p align="center">
  <img src= 'figures/workflow.png'>
</p>


## 🌟 Key Features

### 🔄 Closed-loop Device–Cloud Collaborative Multi-Agent Architecture

EcoAgent deploys:

* **Cloud-based Planning Agent** (LLM reasoning / long-horizon planning)
* **Device-based Execution Agent** (action generation + local tool execution)
* **Device-based Observation Agent** (lightweight verification + screen understanding)

This design enables:

* Lower latency
* Reduced cloud computation
* Privacy-preserving automation
* Closed-loop feedback for higher reliability

## 🧩 System Architecture

```
User → Cloud Planner (Dual-ReACT/Repaln) → Device Executor
                      ↑                                 ↓
                      Device Observer ← Pre-Understanding
```

Cloud does “thinking”, device does “acting + verifying”.

## ⚙️ Installation

### 1️⃣ Clone the repository

```bash
git clone https://github.com/Yi-Biao/EcoAgent.git
cd EcoAgent
```


### 2️⃣ Python Environment

```bash
conda create -n ecoagent python=3.12
conda activate ecoagent
pip install -r requirements.txt
```

### 3️⃣ Download & Configure ADB
✅ **Download ADB**

macOS (recommended via Homebrew):
```
brew install android-platform-tools
```

Or you can download the Platform-tools package for macOS/Linux/Windows:

👉 https://developer.android.google.cn/tools/releases/platform-tools#downloads

✅ **Add ADB to Your PATH**

macOS/Linux:

```
export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools"
```

Windows:

1. Open System Properties → Advanced → Environment Variables
2. Add the path of platform-tools to the `Path` variable like:
```
D:\platform-tools
```

✅ **Verify ADB Installation**

```
adb
```

If you see something like:

```
Android Debug Bridge version 1.0.41
Version 35.0.2-12147458
Installed as /Users/xxxx/Library/Android/sdk/platform-tools//adb
```

then ADB is successfully installed 🎉

### 4️⃣ Download base models of Device-side
✅ **Suggested Models of Device Observer**

[![Qwen2-VL-2B](https://img.shields.io/badge/Qwen2--VL-2B-FF6F61?style=for-the-badge\&logo=huggingface\&logoColor)](https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct)
[![Qwen2.5-VL-3B](https://img.shields.io/badge/Qwen2.5--VL-3B-4CAF50?style=for-the-badge\&logo=huggingface\&logoColor)](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct)
[![Qwen3-VL-2B](https://img.shields.io/badge/Qwen3--VL-2B-FFAA33?style=for-the-badge\&logo=huggingface\&logoColor)](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)

✅ **Supported Models of Device Executor**

[![ShowUI-2B](https://img.shields.io/badge/ShowUI-2B-00C1D4?style=for-the-badge\&logo=huggingface\&logoColor)](https://huggingface.co/showlab/ShowUI-2B)
[![OS-Atlas-4B](https://img.shields.io/badge/OS--Atlas-4B-6A5ACD?style=for-the-badge\&logo=huggingface\&logoColor)](https://huggingface.co/OS-Copilot/OS-Atlas-Pro-4B)
[![UI-TARS-1.5-7B](https://img.shields.io/badge/UI--TARS--1.5-7B-FF4F4F?style=for-the-badge\&logo=huggingface\&logoColor)](https://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B)
[![Qwen3-VL-2B](https://img.shields.io/badge/Qwen3--VL-2B-FFAA33?style=for-the-badge\&logo=huggingface\&logoColor)](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)

### 5️⃣ Develop the device-side base models

```
# Develop your Device Observer
CUDA_VISIBLE_DEVICES=0 \
vllm serve DEVICE_OBSERVER \
  --trust-remote-code \
  --dtype bfloat16 \
  --port 8800 \
  --max-model-len 8192 &

# Develop your Device Executor
CUDA_VISIBLE_DEVICES=0 \
vllm serve DEVICE_EXECUTOR\
  --trust-remote-code \
  --dtype bfloat16 \
  --port 8801 \
  --max-model-len 8192
```

## 📱 Device Support

### Android Emulator

* Tested on **Google Pixel 6**, **[AndroidWorld benchmark](https://github.com/google-research/android_world)**

### Android Device

* Requires **ADB** (USB debugging enabled)

## 🔧 Configuration

EcoAgent uses a unified YAML-based configuration file (`config.yaml`) to control the models.

Below is the recommended configuration template:
```
# ============== Cloud Planner Configuration ==============
llm:
  # OpenAI GPT-4o for planning and replanning
  model_name: "gpt-4o"
  api_url: "https://api.openai.com/v1/chat/completions"
  api_key_env_var: "OPENAI_API_KEY"
  max_retry: 3
  temperature: 0.0
  max_tokens: 2000

# ============== Device Executor Configuration ==============
slm:
  # action prediction
  model_name: "DEVICE_EXECUTOR"
  api_url: "http://127.0.0.1:8801/v1/chat/completions"
  max_retry: 3
  temperature: 0
  max_tokens: 256

# ============== Device Observer Configuration ==============
vision:
  # screen description
  description_model_name: "DEVICE_OBSERVER"
  description_api_url: "http://127.0.0.1:8800/v1/chat/completions"

  # expectation summary
  summary_model_name: "DEVICE_OBSERVER"
  summary_api_url: "http://127.0.0.1:8800/v1/chat/completions"

  max_tokens: 256
  temperature: 0
```

## 🚀 Run EcoAgent

### 1️⃣ Run EcoAgent main loop

```bash
# Choose your agent
python run.py --agent=eco_ui-tars
```

### 2️⃣ Choose the target device

```
Connected devices:
[0] emulator-5554
[1] emulator-5556
Select device by number (0-1):  1
```

### 3️⃣ Input the query

```
Please enter your query: Open Meituan and search for “milk tea”
```

## 📜 Citation

```
@inproceedings{yi2026ecoagent,
  title={EcoAgent: An Efficient Device-Cloud Collaborative Multi-Agent Framework for Mobile Automation},
  author={Yi, Biao and Hu, Xueyu and Chen, Yurun and Zhang, Shengyu and Yang, Hongxia and Wu, Fan},
  booktitle={Proceedings of the AAAI Conference on Artificial Intelligence},
  volume={40},
  number={35},
  pages={29838--29846},
  year={2026}
}
@misc{yi2025ecoagentefficientedgecloudcollaborative,
      title={EcoAgent: An Efficient Edge-Cloud Collaborative Multi-Agent Framework for Mobile Automation}, 
      author={Biao Yi and Xavier Hu and Yurun Chen and Shengyu Zhang and Hongxia Yang and Fan Wu and Fei Wu},
      year={2025},
      eprint={2505.05440},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2505.05440}, 
}
```

## 📨 Contact

Feel free to contact us: biaoyi18@gmail.com
