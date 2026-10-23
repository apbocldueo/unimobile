# Benchmark 插件使用说明

本文档整理了你提到的三类插件：

- 任务初始化（Task Initializer）
- 环境初始化（Environment Initializer）
- 结果评估（Evaluator）

每个插件都说明了：

- 适合什么场景
- 如何使用
- 参数含义
- 常见注意事项
- 示例写法

---

## 一、任务初始化插件

任务初始化插件用于在 benchmark 开始前，生成任务参数。它们通常写在任务定义里，用来把抽象参数变成具体值。

### 1. `random_choice`

**用途**

从一个候选列表中随机选择一个值，适合需要在任务开始时随机生成一个离散参数的场景。

**什么时候适合用**

- 需要随机选择开关状态，例如 `on/off`
- 需要从多个候选项中挑一个作为任务条件
- 需要让任务每次运行时有一点变化，但仍然来自固定集合

**如何使用**

在任务参数初始化配置中，指定 `name: random_choice`，并传入 `options` 列表。

**参数说明**

- `options`：`List[Any]`
  - 必填
  - 候选值列表
  - 不能为空

**返回值**

- 从 `options` 中随机抽取的一个元素

**错误情况**

- 如果没有提供 `options`
- 如果 `options` 为空列表

**示例**

```json
{
  "bluetooth_state": {
    "name": "random_choice",
    "params": {
      "options": ["on", "off"]
    }
  }
}
```

**使用建议**

- 适合搭配 `map_value` 使用
- 如果你要控制随机空间，建议把候选值显式写全

---

### 2. `random_string`

**用途**

生成随机字符串，可设置长度、前缀、后缀和字符集。

**什么时候适合用**

- 需要生成随机用户名、文件名、标识符
- 需要制造不同的测试数据，避免命名冲突
- 需要为文件内容或表单内容注入随机文本

**如何使用**

在任务参数初始化配置中，指定 `name: random_string`，并通过 `params` 配置长度、前缀、后缀和字符集。

**参数说明**

- `length`：`int`
  - 可选，默认 `8`
  - 随机部分长度
- `prefix`：`str | int`
  - 可选，默认空字符串
  - 会被转成字符串
- `suffix`：`str | int`
  - 可选，默认空字符串
  - 会被转成字符串
- `charset`：`str`
  - 可选，默认 `alphanumeric`
  - 字符集或字符集别名

**内置字符集别名**

- `digits`：`0123456789`
- `letters_lower`：小写字母
- `letters_upper`：大写字母
- `letters`：大小写字母
- `alphanumeric`：小写字母 + 数字
- `hex`：十六进制字符

**返回值**

- 拼接后的随机字符串：`prefix + random_part + suffix`

**错误情况**

- `charset` 为空时会报错

**示例**

```json
{
  "temp_name": {
    "name": "random_string",
    "params": {
      "length": 12,
      "prefix": "test_",
      "suffix": ".txt",
      "charset": "letters"
    }
  }
}
```

**使用建议**

- 如果要生成文件名，建议加前缀/后缀来控制格式
- 如果要生成纯数字验证码，可用 `digits`
- 如果要和其他参数联动，可把它作为中间变量传给后续插件

---

### 3. `map_value`

**用途**

把一个输入值按固定映射表转换成另一个值。

**什么时候适合用**

- 前一个初始化器生成了抽象值，后一个插件需要具体值
- 需要把“业务语义值”映射成“系统值”
- 例如把 `on/off` 映射为 `1/0`

**如何使用**

通常与 `random_choice` 配合使用。先生成一个中间变量，再用 `map_value` 把它映射成目标值。

**参数说明**

- `value`：`str`
  - 必填
  - 待映射的输入值
  - 支持占位符渲染结果，例如 `${on_or_off}`
- `map`：`Dict[str, Any]`
  - 必填
  - 映射表，不能为空

**返回值**

- `map[value]` 对应的结果

**错误情况**

- `map` 不是字典或为空
- `value` 在 `map` 中找不到对应键

**示例**

```json
{
  "on_or_off": {
    "name": "random_choice",
    "params": {
      "options": ["off", "on"]
    }
  },
  "bluetooth_enabled": {
    "name": "map_value",
    "params": {
      "value": "${on_or_off}",
      "map": {
        "off": "0",
        "on": "1"
      }
    }
  }
}
```

**使用建议**

- 适合把随机选择结果转换成接口需要的编码值
- 映射表建议保持简单、固定、可读

---

### 4. `calendar_timestamp`

**用途**

生成用于日历类任务的 Unix 时间戳，常见于需要往日程数据库中插入事件的任务初始化阶段。

**什么时候适合用**

- 需要为日历事件生成开始时间和结束时间
- 需要把“固定年月日 + 小时”转换成可写入数据库的时间戳
- 需要生成相对日期，但最终仍然要落成标准时间戳
- 需要给 `start_ts`、`end_ts` 这类字段提供值

**如何使用**

在任务初始化中把 `name` 写成 `calendar_timestamp`，然后通过 `params` 指定日期来源和时间信息。这个插件支持三种日期写法：

- `offset_days`：相对今天偏移几天
- `weekday`：按星期几取日期
- `year + month + day`：直接指定固定年月日

**参数说明**

- `offset_days`：`int`
  - 可选
  - 相对当前日期偏移的天数
  - 例如 `10` 表示 10 天后
- `weekday`：`str`
  - 可选
  - 星期几，如 `monday`、`tuesday`、`wednesday` 等
- `year`：`int`
  - 可选
  - 配合 `month`、`day` 一起使用，表示固定日期
- `month`：`int`
  - 可选
  - 月份
- `day`：`int`
  - 可选
  - 日期
- `hour`：`int`
  - 必填
  - 小时值
  - 可以是 0–23，也可以是 1–12，配合 `time` 使用
- `time`：`str`
  - 可选
  - `am` 或 `pm`
  - 当 `hour` 使用 12 小时制时需要提供
- `role`：`str`
  - 可选，默认 `start`
  - 可取 `start` 或 `end`
  - `end` 表示在开始时间基础上加持续时间
- `duration_mins`：`int`
  - 可选，默认 `60`
  - 仅在 `role=end` 时生效
- `unit`：`str`
  - 可选，默认 `seconds`
  - 可取 `ms`、`millisecond`、`milliseconds`
  - 用于决定返回秒级还是毫秒级时间戳

**返回值**

- Unix 时间戳整数
- 默认单位是秒；设置 `unit=ms` 时返回毫秒

**注意事项**

- 如果任务里要求的是固定日期，建议直接使用 `year + month + day`
- `offset_days` 适合相对日期，不适合严格固定某一天的任务
- `hour=1` 这种边界时间在时区转换时更容易暴露问题，因此更推荐明确指定日期和时区一致的生成方式
- `role=end` 不是单独的一天，它是在开始时间基础上顺延 `duration_mins`

**示例**

固定日期的开始时间：

```json
{
  "event_start": {
    "name": "calendar_timestamp",
    "params": {
      "year": 2026,
      "month": 6,
      "day": 14,
      "hour": 1,
      "time": "am"
    }
  }
}
```

固定日期的结束时间：

```json
{
  "event_end": {
    "name": "calendar_timestamp",
    "params": {
      "year": 2026,
      "month": 6,
      "day": 14,
      "hour": 1,
      "time": "am",
      "role": "end",
      "duration_mins": 30
    }
  }
}
```

相对日期的事件时间：

```json
{
  "event_start": {
    "name": "calendar_timestamp",
    "params": {
      "offset_days": 10,
      "hour": 14
    }
  }
}
```

**使用建议**

- 日历类任务优先用这个插件生成 `start_ts` / `end_ts`
- 如果你要控制结果稳定性，优先使用固定年月日，而不是 `offset_days`
- 与 `random_choice`、`map_value` 配合时，可以先生成日期相关变量，再生成最终时间戳

---

## 二、环境初始化插件

环境初始化插件用于 benchmark 执行前对设备环境做准备，例如清理目录、推送文件、执行 shell 命令、清空 App 数据等。

### 1. `clear_directoty`

**插件注册名**：`benchmark.environment.reset/android_reset_clear_directory`

**用途**

清空 Android 设备上某个目录下的所有内容。

**什么时候适合用**

- 需要清理上一次测试留下的文件
- 需要保证某个目录在任务开始前是干净的
- 文件管理、下载、图片、文档类任务经常需要它

**如何使用**

在环境初始化配置中传入目标目录路径 `phone_folder_path`。

**参数说明**

- `phone_folder_path`：`str`
  - 必填
  - 设备上的目录路径
- `media_scan`：`bool`
  - 可选，默认 `true`
  - 清理后是否触发媒体扫描刷新

**执行逻辑**

1. 执行 `rm -rf <path>/*`
2. 用 `ls` 检查目录是否可访问
3. 如果 `media_scan=true`，触发媒体扫描

**返回值**

- 成功返回 `true`
- 任一步失败返回 `false`

**注意事项**

- 它只清空目录内容，不删除目录本身
- 路径会把 `\` 统一转换成 `/`
- `media_scan` 对图片、视频、音频文件很有用

**示例**

```json
{
  "name": "android_reset_clear_directory",
  "params": {
    "phone_folder_path": "/storage/emulated/0/Download",
    "media_scan": true
  }
}
```

---

### 2. `app_warm_reset`

**插件注册名**：`benchmark.environment.reset/android_app_warm_reset`

**用途**

对 App 做“暖重置”，本质是只执行 `am force-stop`，不清数据。

**什么时候适合用**

- 你只想结束 App 进程，但保留登录状态和本地数据
- 想清理任务栈，让下次启动更干净
- 不希望像 `pm clear` 那样把数据全部清掉

**如何使用**

传入应用逻辑名 `app`，插件会从设备的 `app_package_names` 映射中解析出包名。

**参数说明**

- `app`：`str`
  - 必填
  - 应用逻辑名，例如 `contacts`

**前置条件**

- `meta` 中必须有 `device`
- `device` 必须有 `app_package_names` 映射

**返回值**

- 成功返回 `true`
- 失败返回 `false`

**注意事项**

- 这个插件不会清除应用数据
- 如果传入的应用名不在映射中，会直接失败

**示例**

```json
{
  "name": "android_app_warm_reset",
  "params": {
    "app": "contacts"
  }
}
```

---

### 3. `push_file`

**插件注册名**：`benchmark.environment.injection/android_injection_push_file`

**用途**

把宿主机上的文件推送到 Android 设备上。

**什么时候适合用**

- 需要预置图片、视频、音频、文档、压缩包等文件
- 需要模拟用户手机上已有的资源文件
- 需要为文件类任务准备初始素材

**如何使用**

在 `files` 中写入一个文件列表，每个文件包含本地路径和设备路径。

**参数说明**

- `files`：`List[Dict[str, Any]]`
  - 必填
  - 文件列表
  - 每个元素至少包含：
    - `local_path`：宿主机路径
    - `device_path`：设备路径
- `media_scan`：`bool`
  - 可选，默认 `true`
  - 是否在推送后触发媒体扫描

**每个文件项可选字段**

- `media_scan`：`bool`
  - 单个文件级别覆盖全局 `media_scan`

**执行逻辑**

1. 检查本地文件是否存在
2. 确保设备端目标目录存在
3. 执行 `push_file`
4. 按需触发媒体扫描

**返回值**

- 成功返回 `true`
- 任一文件失败则返回 `false`

**注意事项**

- `device_path` 的父目录会自动创建
- 如果文件不存在，会直接失败
- 对媒体类资源建议保持 `media_scan=true`

**示例**

```json
{
  "name": "android_injection_push_file",
  "params": {
    "files": [
      {
        "local_path": "assets/sample.jpg",
        "device_path": "/storage/emulated/0/Pictures/sample.jpg"
      },
      {
        "local_path": "assets/demo.mp3",
        "device_path": "/storage/emulated/0/Music/demo.mp3",
        "media_scan": true
      }
    ],
    "media_scan": true
  }
}
```

---

### 4. `android_shell_execute`

**插件注册名**：`benchmark.environment.injection/android_shell_execute`

**用途**

在 Android 设备上执行一个或多个 shell 命令。

**什么时候适合用**

- 需要执行系统级准备命令
- 需要创建/清理系统内容提供器数据
- 需要运行 `pm clear`、`content insert`、`settings put` 等命令
- 其他专用插件不够用时，作为通用兜底工具

**如何使用**

把命令写到 `commands` 中，可以是单个字符串，也可以是字符串列表。

**参数说明**

- `commands`：`str | List[str]`
  - 必填
  - 一个命令或多个命令
- `ignore_errors`：`bool`
  - 可选，默认 `false`
  - 单条命令失败后是否继续执行后续命令

**执行逻辑**

- 如果 `commands` 是字符串，会自动转成单元素列表
- 按顺序逐条执行
- 当 `ignore_errors=false` 时，遇到第一条失败命令就中止
- 当 `ignore_errors=true` 时，会跳过失败继续执行

**返回值**

- 全部成功返回 `true`
- 有失败且 `ignore_errors=false` 返回 `false`

**注意事项**

- 这是低层能力，使用时要确保命令安全、可重复
- 适合做高级初始化，不适合替代清晰的专用插件

**示例**

```json
{
  "name": "android_shell_execute",
  "params": {
    "commands": [
      "pm clear com.android.providers.contacts",
      "settings put global airplane_mode_on 0"
    ],
    "ignore_errors": false
  }
}
```

---

### 5. `reset_app_data`

**插件注册名**：`benchmark.environment.reset/android_reset_reset_app_data`

**用途**

清空指定 Android 应用的数据，相当于系统设置中的“清除存储”。

**什么时候适合用**

- 需要把 App 恢复到刚安装后的状态
- 需要清掉登录信息、缓存、数据库、偏好设置
- 需要确保每次 benchmark 的初始状态完全一致

**如何使用**

可以直接传包名，也可以传逻辑应用名 `app`。

**参数说明**

- `package`：`str`
  - 可选
  - 直接指定包名
- `app`：`str`
  - 可选
  - 逻辑应用名，由 `device.app_package_names` 映射成包名

**二选一要求**

- `package` 和 `app` 至少提供一个

**执行逻辑**

1. 解析出包名
2. 先执行 `am force-stop <package>`
3. 再执行 `pm clear <package>`
4. 检查输出是否成功

**返回值**

- 成功返回 `true`
- 失败返回 `false`

**注意事项**

- 和 `app_warm_reset` 的区别是：这个会清数据
- 若应用名映射不存在，会失败
- 如果 `pm clear` 输出不是标准 `Success`，会记录警告

**示例**

```json
{
  "name": "android_reset_reset_app_data",
  "params": {
    "app": "contacts"
  }
}
```

或者：

```json
{
  "name": "android_reset_reset_app_data",
  "params": {
    "package": "com.google.android.contacts"
  }
}
```

---

### 6. `create_file`

**插件注册名**：`benchmark.environment.injection/android_injection_create_file`

**用途**

在 Android 设备上创建文件，并可写入文本内容。

**什么时候适合用**

- 需要预先创建空文件
- 需要创建简单文本文件
- 需要模拟用户本地文档、笔记、配置文件
- 需要为后续编辑、读取、搜索类任务准备文件

**如何使用**

传入目标路径和文件内容。可以直接给完整路径 `phone_file_path`，也可以用 `folder_path + file_name` 组合。

**参数说明**

- `phone_file_path`：`str`
  - 可选，但如果不传，则必须传 `folder_path` 和 `file_name`
  - 文件完整路径
- `folder_path`：`str`
  - 可选
  - 目标目录
- `file_name`：`str`
  - 可选
  - 文件名
- `content`：`str`
  - 可选，默认空字符串
  - 文件内容
  - 如果为空，则只创建空文件

**执行逻辑**

- 如果 `content` 为空：执行 `touch`
- 如果 `content` 非空：执行 `echo "..." > file`
- 最后用 `ls` 验证文件是否存在

**返回值**

- 成功返回 `true`
- 失败返回 `false`

**注意事项**

- 该实现更适合简单文本内容，不适合复杂二进制文件
- 内容中如果有双引号，会先做简单转义
- 如果文件内容很复杂，建议使用 `push_file`

**示例**

```json
{
  "name": "android_injection_create_file",
  "params": {
    "phone_file_path": "/storage/emulated/0/Documents/note.txt",
    "content": "hello world"
  }
}
```

或者：

```json
{
  "name": "android_injection_create_file",
  "params": {
    "folder_path": "/storage/emulated/0/Documents",
    "file_name": "note.txt",
    "content": "hello world"
  }
}
```

---

## 三、结果评估插件

结果评估插件用于判断任务是否完成。它们会在任务结束后读取设备状态、文件内容、或调用多模态模型来做最终判定。

### 1. `composite`

**用途**

把多个评估规则组合成一个最终判定结果。它本身不直接判断内容，而是负责协调多个子规则，并根据组合逻辑输出最终的通过或失败。

**什么时候适合用**

- 一个任务需要同时满足多个条件
- 一个任务允许多种完成方式
- 需要按顺序验证多个步骤
- 需要把文本评估、文件评估、视觉评估等多个检查统一起来

**如何使用**

在 `evaluator` 中把 `name` 写成 `composite`，并在 `params` 里提供：

- `logic`：组合逻辑
- `rules`：子规则列表

**参数说明**

- `logic`：`str`
  - 必填
  - 组合逻辑
  - 常见值：`AND`、`OR`、`SEQUENCE`
- `rules`：`List[Dict[str, Any]]`
  - 必填
  - 子评估规则列表
  - 每个子规则都需要有自己的 `name` 和 `params`

**返回值**

- 所有子规则按逻辑组合后得到最终的 `EvalResult`

**注意事项**

- `composite` 不是具体的判断方法，而是组合器
- `rules` 里的每个子规则都应该写成完整的评估器配置
- 组合逻辑的大小写通常不敏感，但建议统一写成大写，便于阅读

**示例**

```json
{
  "name": "composite",
  "params": {
    "logic": "AND",
    "rules": [
      {
        "name": "llm_output_judge",
        "params": {
          "method": "trajectory_expected_match",
          "match": "contains",
          "expected": "Gym Session",
          "ignore_case": true
        }
      },
      {
        "name": "llm_output_judge",
        "params": {
          "method": "trajectory_expected_match",
          "match": "contains",
          "expected": "Lunch with Client",
          "ignore_case": true
        }
      }
    ]
  }
}
```

### 组合逻辑说明

在 AndroidWorld 这类任务里，评估经常不是“单条规则判断”，而是“多个条件一起判断”。因此文档里最需要解释的是：`logic` 决定这些子规则之间是什么关系。

#### `AND`

- 表示**全部子规则都要通过**
- 任意一个失败，最终失败
- 适合“多个结果都必须成立”的任务

#### `OR`

- 表示**子规则中只要有一个通过即可**
- 全部失败才算失败
- 适合“满足任意一个条件就算完成”的任务

#### `SEQUENCE`

- 表示**子规则需要按顺序成立**
- 关注的是先后顺序，而不仅仅是是否都满足
- 适合步骤型、流程型、轨迹型任务

### 什么时候用哪种逻辑

- 任务要求多个结果同时满足：用 `AND`
- 任务允许多种完成路径，满足其一即可：用 `OR`
- 任务强调操作顺序或事件顺序：用 `SEQUENCE`

### 评估配置里常见字段

- `name`：评估器名称，例如 `composite`、`llm_output_judge`、`system_state`、`multi_image_qa`
- `params`：评估器参数对象
- `logic`：组合逻辑，只在 `composite` 中使用
- `rules`：子规则列表，只在 `composite` 中使用
- `method`：具体评估方法，例如 `trajectory_expected_match`、`file_content_match`
- `match`：匹配方式，例如 `contains`、`exact`
- `expected`：期望文本或模式
- `ignore_case`：是否忽略大小写

### 评估写法说明

你给的 `chunkData/40.json` 和 `chunkData/80.json` 中，评估部分经常写成 `composite`，并通过 `logic: AND` 组合多个 `llm_output_judge` 子规则。这种写法的含义是：

1. 先分别执行每个子规则
2. 再根据 `logic` 决定最终结果

这种结构适合把“多个小判定”合并成“一个总判定”，是复杂任务里最常见的评估方式。

---

### `composite`

**用途**

`composite` 是组合评估器。它本身不直接判断任务是否完成，而是把多个子评估规则组合起来，最终统一输出一个通过或失败结果。

**什么时候适合用**

- 一个任务需要同时满足多个条件
- 一个任务允许多种完成方式
- 需要按顺序验证多个步骤
- 需要把文本评估、文件评估、视觉评估等多个检查统一起来

**如何使用**

在 `evaluator` 中将 `name` 写为 `composite`，并在 `params` 中提供：

- `logic`：组合逻辑
- `rules`：子规则列表

**参数说明**

- `logic`：`str`
  - 必填
  - 组合逻辑
  - 常见值：`AND`、`OR`、`SEQUENCE`
- `rules`：`List[Dict[str, Any]]`
  - 必填
  - 子评估规则列表
  - 每个子规则都必须是一个完整评估器配置，包含自己的 `name` 和 `params`

**返回值**

- 所有子规则按 `logic` 组合后，得到最终 `EvalResult`

**注意事项**

- `composite` 只是组合器，不是具体判断方法
- `rules` 里的每个子规则都应独立可读、可执行
- 常见的做法是将多个 `llm_output_judge`、`system_state` 或 `multi_image_qa` 组合在一起

**示例**

```json
{
  "name": "composite",
  "params": {
    "logic": "AND",
    "rules": [
      {
        "name": "llm_output_judge",
        "params": {
          "method": "trajectory_expected_match",
          "match": "contains",
          "expected": "Gym Session",
          "ignore_case": true
        }
      },
      {
        "name": "llm_output_judge",
        "params": {
          "method": "trajectory_expected_match",
          "match": "contains",
          "expected": "Lunch with Client",
          "ignore_case": true
        }
      }
    ]
  }
}
```

**组合逻辑说明**

`logic` 决定 `rules` 之间的关系：

#### `AND`

- 表示所有子规则都必须通过
- 任何一个失败，最终就失败
- 适合“多个条件都必须满足”的任务

#### `OR`

- 表示子规则中只要有一个通过即可
- 只有全部失败时，最终才失败
- 适合“满足任一条件即可完成”的任务

#### `SEQUENCE`

- 表示子规则需要按顺序成立
- 关注的不只是结果，还包括顺序
- 适合流程型、步骤型、轨迹型任务

**什么时候用哪种逻辑**

- 任务要求多个结果同时满足：用 `AND`
- 任务允许多种完成路径，满足其一即可：用 `OR`
- 任务强调操作顺序或事件顺序：用 `SEQUENCE`

**评估写法说明**

在你给的 `chunkData/40.json` 和 `chunkData/80.json` 中，评估部分经常写成 `composite`，并通过 `logic: AND` 组合多个子规则。这种结构表示：

1. 先分别执行每个子规则
2. 再根据 `logic` 统一判断最终结果

---

### `llm_output_judge`

**用途**

根据模型输出文本对任务结果进行判定。它通常从轨迹中提取最后一段可判断文本，再与期望值进行匹配。

**什么时候适合用**

- 任务答案是文本、短语、数字、布尔值
- 需要从 agent 的输出中抽取答案并判断是否正确
- 需要支持 `contains`、`exact`、`boolean`、`first_integer` 这类匹配方式

**如何使用**

在 `composite` 的 `rules` 中，或者作为单独评估器使用时，将 `name` 写为 `llm_output_judge`，并在 `params` 中提供 `method` 等参数。

**参数说明**

- `method`：`str`
  - 必填
  - 具体判定方式
  - 常见值：`trajectory_expected_match`
- `match`：`str`
  - 可选
  - 仅在具体方法支持时使用
  - 常见值：`boolean`、`first_integer`、`exact`、`contains`
- `expected`：`str | int | bool`
  - 必填或按方法要求提供
  - 期望值
- `source`：`str`
  - 可选，默认 `last_step_thought`
  - 指定从轨迹中抽取哪一部分文本
- `ignore_case`：`bool`
  - 可选
  - 文本匹配时是否忽略大小写

**返回值**

- 依据匹配结果返回 `EvalResult`

**注意事项**

- 这是文本型评估，不是视觉评估
- 如果任务答案直接体现在 agent 的输出中，这类评估最合适

**示例**

```json
{
  "name": "llm_output_judge",
  "params": {
    "method": "trajectory_expected_match",
    "match": "contains",
    "expected": "Gym Session",
    "ignore_case": true
  }
}
```

---

### `system_state`

**用途**

读取设备上的系统状态或文件状态，并据此进行评估。常见的子方法包括 `file_content_match`。

**什么时候适合用**

- 需要检查设备文件是否写入成功
- 需要确认系统状态是否改变
- 需要验证内容是否与预期一致

**如何使用**

在 `composite` 的 `rules` 中，或者作为单独评估器使用时，将 `name` 写为 `system_state`，并通过 `method` 指定具体检查方法。

**参数说明**

- `method`：`str`
  - 必填
  - 当前常见值：`file_content_match`
- 其他参数由具体 `method` 决定

**返回值**

- 依据具体方法返回 `EvalResult`

**示例**

包含匹配：

**用途**

读取设备上的文件内容，并与目标内容进行匹配。

**什么时候适合用**

- 需要确认文件是否被正确创建或修改
- 需要验证文件内容是否包含某段文本
- 需要验证文件是否完全等于预期内容

**如何使用**

传入 `file_path` 和 `content`，并可选设置 `match` 模式。

**参数说明**

- `file_path`：`str`
  - 必填
  - 设备上的文件路径
- `content`：`str`
  - 必填
  - 期望内容
- `match`：`str`
  - 可选，默认 `contains`
  - 支持：
    - `contains`：只要求包含
    - `exact`：要求全文精确一致

**执行逻辑**

1. 执行 `cat <file_path>`
2. 如果文件不存在，直接失败
3. 若 `match=exact`，则做归一化后精确比较
4. 若 `match=contains`，则检查是否包含目标文本

**返回值**

- 成功返回 `EvalResult(is_pass=True, ...)`
- 失败返回 `EvalResult(is_pass=False, ...)`

**注意事项**

- `exact` 会对换行和首尾空白做标准化处理
- 默认 `contains` 更宽松，适合验证文件中是否有指定片段

**示例**

包含匹配：

```json
{
  "name": "system_state",
  "params": {
    "method": "file_content_match",
    "file_path": "/storage/emulated/0/Documents/note.txt",
    "content": "hello"
  }
}
```

精确匹配：

```json
{
  "name": "system_state",
  "params": {
    "method": "file_content_match",
    "file_path": "/storage/emulated/0/Documents/note.txt",
    "content": "hello world",
    "match": "exact"
  }
}
```

---

### 4. `multi_image_qa`

**用途**

把多张截图一次性交给多模态模型，让模型根据提示词对任务结果做统一判断。

**什么时候适合用**

- 任务结果不能只靠文本或 shell 输出判断
- 需要检查多个步骤的界面演变
- 需要评估复杂 UI 状态、可视化变化、屏幕内容是否达标
- 需要结合轨迹截图和参考图进行综合判断

**如何使用**

传入 `prompt` 和 `images`。`images` 是核心参数，决定要送哪些图片给模型。

**参数说明**

- `prompt`：`str`
  - 必填
  - 让模型判断什么
- `images`：`str | list | dict`
  - 可选，但实际评估几乎总是需要
  - 用于选择截图来源
- `max_images`：`int`
  - 可选，默认 `10`
  - 限制最多送多少张图
  - `0` 表示不限制
- `labels`：`List[str]`
  - 可选
  - 为每张图自定义标签
- `use_marked`：`bool`
  - 可选，默认 `false`
  - 优先使用带标注的截图

**`images` 的用法**

### 1）字符串形式

- `"all"`：发送轨迹中的所有截图
- `"last"` 或 `"last:1"`：发送最后一张
- `"last:4"`：发送最后 4 张

### 2）列表形式

- 纯数字列表：表示轨迹步骤号，例如 `[1, -1]`
- 纯字符串列表：表示宿主机图片路径，例如 `[
  "ref/a.png"
]`

### 3）对象形式

可以组合轨迹、文件、实时截图：

- `trajectory`：轨迹选择器
- `files`：本地图片路径列表
- `final`：是否附加当前设备实时截图

**执行逻辑**

1. 解析 `images`
2. 从轨迹、文件、实时截图中收集图片路径
3. 构造多图提示词
4. 调用 VLM
5. 读取模型返回值，必须以 `PASS:` 或 `FAIL:` 开头

**返回值**

- 模型判定通过：`EvalResult(is_pass=True, ...)`
- 模型判定失败：`EvalResult(is_pass=False, ...)`
- 如果模型返回格式不对，也会失败

**注意事项**

- 这是主观性更强的评估方式，适合 UI 结果判断
- 模型输出必须遵守 `PASS:` / `FAIL:` 格式
- 当 `final=true` 时，当前设备需要可截图
- `max_images` 过小时可能会裁掉前面的图，只保留后面的图

**示例**

只评估最后一张截图：

```json
{
  "name": "multi_image_qa",
  "params": {
    "prompt": "请判断最后一张截图是否显示文件已成功打开。",
    "images": "last"
  }
}
```

评估所有步骤：

```json
{
  "name": "multi_image_qa",
  "params": {
    "prompt": "请判断操作流程是否完整且最终页面正确。",
    "images": "all",
    "max_images": 0
  }
}
```

参考图 + 实时屏幕：

```json
{
  "name": "multi_image_qa",
  "params": {
    "prompt": "请判断当前界面是否和参考图一致。",
    "images": {
      "files": ["benchmarks/ref.png"],
      "final": true
    }
  }
}
```

---

## 四、如何选择插件

### 任务初始化怎么选

- 随机挑一个值：`random_choice`
- 生成随机字符串：`random_string`
- 把一个值映射成另一个值：`map_value`

### 环境初始化怎么选

- 清空目录内容：`clear_directoty`
- 只结束 App 进程，不清数据：`app_warm_reset`
- 把宿主机文件推到设备：`push_file`
- 执行任意 shell 命令：`android_shell_execute`
- 清空 App 数据：`reset_app_data`
- 在设备上创建简单文本文件：`create_file`

### 结果评估怎么选

- 终态可用 shell 文本判断：`adb_shell_match`
- 检查设备文件内容：`file_content_match`
- 需要结合多张截图做视觉判断：`multi_image_qa`

---

## 五、实践建议

1. **优先使用专用插件**，只有在专用插件不够时再用 `android_shell_execute`。
2. **文件类任务优先用 `push_file`**，复杂内容或二进制文件不要依赖 `create_file`。
3. **重置 App 时区分“暖重置”和“清数据”**：
   - `app_warm_reset`：只停进程
   - `reset_app_data`：彻底清空数据
4. **评估方式尽量和任务目标一致**：
   - 文本就用文本评估
   - 文件就用文件评估
   - 界面就用视觉评估

---

## 六、速查表

| 插件 | 类别 | 主要用途 |
|---|---|---|
| `random_choice` | 任务初始化 | 从候选项中随机选一个 |
| `random_string` | 任务初始化 | 生成随机字符串 |
| `map_value` | 任务初始化 | 进行固定值映射 |
| `clear_directoty` | 环境初始化 | 清空设备目录 |
| `app_warm_reset` | 环境初始化 | 只 force-stop App |
| `push_file` | 环境初始化 | 推送宿主机文件到设备 |
| `android_shell_execute` | 环境初始化 | 执行设备 shell 命令 |
| `reset_app_data` | 环境初始化 | 清除 App 数据 |
| `create_file` | 环境初始化 | 在设备上创建文件 |
| `adb_shell_match` | 结果评估 | shell 输出正则匹配 |
| `file_content_match` | 结果评估 | 文件内容匹配 |
| `multi_image_qa` | 结果评估 | 多图视觉判定 |

---
