# DISPLIB 数据结构原位对照表

这份文档严格保留了原本被“挤成一整段”的 JSON 顺序。在原始代码片段的正下方，我用中文解释了这一段字符到底是干什么的。

## 1. 车辆与路线架构 (Trains & Operations)

JSON 开头包裹了全局最庞大的数据 `trains` 数组：
```json
{"trains":[
```
> 代表整个系统接入了 2 辆列车的数据清单（用逗号分隔了两个巨大的数组）。

### 🚂 列车 0 (Train 0) 的原样路线
```json
  [
    {"start_ub":0, "min_duration":0, "successors":[1]},
```
> **Train 0 第 0 步 (起点)**: `start_ub:0` 意味着时间必须从0秒算起。`min_duration:0` 代表发车这一动作不耗时。做完后 `successors:[1]` 要求系统去执行第 1 步。

```json
    {"min_duration":5, "resources":[{"resource":"r0"}], "successors":[2]},
```
> **Train 0 第 1 步**: `min_duration:5` 行程耗时5分钟。执行期间，申请强制霸占名为 `r0` 的铁轨系统。做完去第 2 步。

```json
    {"min_duration":5, "resources":[{"resource":"r1"}], "successors":[3]},
```
> **Train 0 第 2 步**: 紧接着，这辆车又继续开了 5 分钟，这次它占用的铁轨换成了 `r1`。做完去第 3 步。

```json
    {"min_duration":5, "successors":[]}
  ],
```
> **Train 0 第 3 步 (终点)**: 最后花了 5 分钟到达。因为 `successors:[]` 里面是空的，代表这列火车在此退出系统，路线完结！

---

### 🚂 列车 1 (Train 1) 的原样路线
*(注意对比 Train 1 和 Train 0 申请铁路（r0 和 r1）的顺序，正好相反，构成了相撞问题。)*
```json
  [
    {"start_ub":0, "min_duration":0, "successors":[1]},
```
> **Train 1 第 0 步 (起点)**: 和第一辆车一样，必须从时刻 0 准备发车。

```json
    {"min_duration":5, "resources":[{"resource":"r1"}], "successors":[2]},
```
> **Train 1 第 1 步**: 耗时5分钟跑路。但请注意，它最开始申请占去的是 `r1` 轨道！

```json
    {"min_duration":5, "resources":[{"resource":"r0"}], "successors":[3]},
```
> **Train 1 第 2 步**: 跑完上段路后，它跑出来霸占 `r0` 轨道继续开5分钟。

```json
    {"min_duration":5, "successors":[]}
  ]
],
```
> **Train 1 第 3 步 (终点)**: 最终跑完退出。两辆车的整个数组在这里用 `]` 彻底被关闭完结。

---

## 2. 目标函数算分机制 (Objective)

看完车了，紧接着原本那段乱码来到了最后一部分：
```json
"objective":[
```
> 这是竞赛的目标系统。告诉我们最后评分表怎么算。

```json
  {"type":"op_delay", "train":0, "operation":3, "threshold":0, "coeff":1},
```
> **考核单 1 (针对 Train 0)**:
> 考核类型 `op_delay`（延迟惩罚）。它抽查的对象是 `train:0`（列车0）的第 `operation:3` 步（也就是我们刚刚讲的终点站到达时刻）。要求它必须在时刻 `threshold:0`（0分0秒）以前到达。如果晚点，每一秒钟扣 `coeff:1`（系数为 1，即乘 1 计分）。

```json
  {"type":"op_delay", "train":1, "operation":3, "threshold":0, "coeff":1}
]}
```
> **考核单 2 (针对 Train 1)**:
> 同理，盯着列车 1 到终点的时间，依然要求它 0点准达，一样是迟到 1秒 扣 1分。

---
最后，这整个 JSON 就是靠最外面的一个巨大 `{ }` 将这两大块（车子排班、记分规则）紧紧包裹起来，这就是你那段数据最原始的缩影。
