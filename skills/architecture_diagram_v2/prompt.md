---
name: architecture_diagram_v2
version: 2.1.0
description: 通用架构图自动生成技能，LLM全权自主设计完整HTML+CSS代码（布局/层级/配色/动画/交互），工具仅负责本地文件存储、浏览器iframe预览、异常兜底模板。支持四层产品架构、微服务网格、分布式拓扑、数据流图、业务流程图、时序图全类型架构可视化。
author: LLM Visual Skill
scene: 产品架构梳理、技术架构汇报、系统分层拆解、业务流程可视化
---

# 一、技能权责边界（强制遵守）
1. LLM 职责（全权控制可视化内容）
   - 解析用户自然语言需求，自动拆解业务/技术分层、模块、依赖关系；
   - 自主选择布局：Flex分层纵向架构 / Grid网格微服务 / 绝对定位拓扑数据流；
   - 自定义全套视觉：色系、圆角、阴影、边框、渐变、hover过渡动画、字体间距；
   - 编写**完整独立HTML文档**，内置全部CSS，不依赖外部JS/图片/CDN资源；
   - 适配PC/移动端响应式，保证文字清晰、模块区分度强；
2. 工具 generate_architecture_diagram_v2 职责（仅执行存储渲染，无权修改内容）
   - 接收LLM输出的完整HTML字符串，写入本地outputs目录；
   - 自动唤起本地浏览器/iframe预览页面；
   - 仅在LLM未传入合法html_content时，加载极简空白兜底模板；
   - 返回文件绝对路径、预览访问链接、执行状态。

# 二、需求识别触发规则
满足以下任意用户输入，立即启用本技能，无需追问补充信息：
1. 关键词：画XX架构图、系统分层、产品宏观架构、微服务架构、技术底座、业务流程图、数据流、拓扑图、时序图、架构可视化；
2. 模糊需求：梳理整体结构、画出模块关系、可视化系统框架；
3. 限定场景：APP架构、小程序生态、后台系统、中台架构、分布式服务。

# 三、架构拆解通用逻辑（按需自适应调整层级数量，不强制四层）
## 场景1：互联网产品宏观分层架构（APP/平台/小程序生态，优先纵向Flex布局）
自上而下标准分层逻辑，可按需增删层级：
1. 接入终端层：多端客户端、硬件设备、第三方渠道入口；
2. 核心业务应用层：用户可见业务模块、功能中心、场景服务；
3. 公共中台能力层：复用通用组件、账号、IM、支付、AI、风控、消息、权限；
4. 底层基础设施层：云资源、存储、数据库、网络、运维、数据平台。

## 场景2：后端微服务架构（Grid网格布局）
分层：网关层 → 业务微服务集群 → 中间件层 → 数据持久层

## 场景3：分布式/数据流拓扑（绝对定位+连接线）
绘制上下游依赖、数据流向箭头、跨服务交互链路

# 四、HTML+CSS 强制编码规范（输出前自检）
## 4.1 文档完整性校验（不满足则重写）
- 必须包含 `<!DOCTYPE html>`、完整 `<html><head><body>` 闭合标签；
- 全部样式写在内部 `<style>` 标签内，禁止外部样式表；
- 禁止引用外部图片、字体、CDN资源，纯原生CSS实现视觉效果；
- 不引入第三方JS库（html2canvas由前端预览容器内置，无需手动引入）。

## 4.2 布局与响应式规范
1. 纵向分层架构：使用Flex弹性布局，模块自动换行适配窄屏；
2. 微服务集群：CSS Grid网格自动均分；
3. 拓扑/流程图：支持绝对定位+伪元素绘制连线、流向箭头；
4. 全局基础样式统一：重置margin/padding/box-sizing，适配Windows/Mac中文字体。

## 4.3 视觉风格规范（默认商务极简风，用户要求可自定义科技/简约深色）
1. 分层架构固定低饱和专业配色（无特殊要求严格使用）：
   终端层：浅绿 #e8f5e9 ｜业务层：浅蓝 #e3f2fd ｜中台层：浅紫 #f3e5f5 ｜底座层：浅橙 #fff3e0
2. 模块卡片：白色底色、轻微阴影、8px圆角；层级容器12px圆角、带对应色系边框；
3. 文字规范：层级标题加粗大号字体，模块副标题常规字，备注说明浅灰色小字；
4. 可选增强交互：添加hover上浮、背景色渐变过渡动画，禁止花哨卡通/手绘风格。

## 4.4 页面固定标配元素
1. 页面顶部居中大标题：{产品名称} 宏观架构图；
2. 每个层级独立标题，底部标注层级说明；
3. 页面最底部居中小字备注：基于公开行业信息梳理通用架构；
4. 整体容器最大宽度1400px，左右留白，居中展示。

# 五、工具调用完整流程（标准化执行步骤，不可颠倒）
## Step1：解析用户需求
提取系统名称、架构类型、需要展示的模块、特殊样式要求；
## Step2：自主拆解完整架构模块树
梳理每层包含的子模块、模块功能说明；
## Step3：生成完整可独立运行HTML字符串
严格遵循上文编码规范，内置全部样式、分层模块；
## Step4：调用工具 generate_architecture_diagram_v2 传参规则
### 参数必填/可选说明
1. user_request【必填】：用户原始完整提问文本；
2. html_content【核心推荐传入】：Step3生成的完整HTML全文字符串；
3. title【推荐传入】：架构图完整标题，无则自动从user_request截取生成；
4. output_name【可选】：自定义输出html文件名，默认architecture；

### 调用示例模板
```
generate_architecture_diagram_v2(
    user_request="绘制微信完整宏观产品架构图",
    html_content="<!DOCTYPE html><html lang='zh-CN'>...完整代码...</html>",
    title="微信宏观产品架构图",
    output_name="wechat_arch"
)
```
## Step5：工具执行完成后，标准化回复用户
1. 文本解读：分层文字说明架构设计逻辑、每层核心作用；
2. 返回预览地址：架构文件本地预览链接 /outputs/{output_name}.html；
3. 使用提示：页面预览后可直接导出高清PNG图片。

# 六、强约束与禁止项
## 禁止行为
1. 禁止仅输出JSON结构、交由工具拼接HTML；必须LLM原生生成完整页面；
2. 禁止手绘、二次元、卡通、厚重艺术风，正式架构统一极简商务；
3. 禁止缺失层级标题、底部备注、自适应布局；
4. 禁止HTML代码片段、无闭合标签、缺失DOCTYPE；
5. 禁止将样式写在行内style为主，统一收拢至head内style标签便于统一修改；

## 强制兜底规则
1. 若用户需求模糊、缺少业务信息，基于行业通用标准补充合理模块；
2. 若生成HTML校验不完整，自动补全文档结构后再调用工具；
3. 用户要求深色/科技渐变风格时，可替换全套配色，保留分层逻辑不变。

# 七、内置参考模板（快速复用，按需修改模块名称）
## 模板1：四层纵向产品架构（默认首选）
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{替换为架构标题}</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
            background: #f5f6fa; min-height: 100vh; padding: 40px 20px;
        }
        .container { max-width: 1400px; margin:0 auto; }
        .main-title {
            text-align: center; font-size: 32px; font-weight: 700; color: #1a1a2e;
            margin-bottom: 40px; letter-spacing: 1px;
        }
        .layer {
            border-radius: 12px; border: 2px solid; padding: 24px; margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        .layer-terminal { background:#e8f5e9; border-color:#81c784; }
        .layer-business { background:#e3f2fd; border-color:#64b5f6; }
        .layer-middleware { background:#f3e5f5; border-color:#ba68c8; }
        .layer-infra { background:#fff3e0; border-color:#ffb74d; }
        .layer-title {
            font-size: 18px; font-weight: 700; margin-bottom: 16px;
            padding-bottom: 8px; border-bottom: 1px solid rgba(0,0,0,0.1);
        }
        .cards { display: flex; flex-wrap: wrap; gap: 12px; }
        .card {
            flex: 1 1 200px; min-width: 160px; max-width: 280px;
            background: #fff; border-radius: 8px; padding: 16px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            transition: transform 0.2s ease;
        }
        .card:hover { transform: translateY(-3px); }
        .card-title { font-size: 15px; font-weight: 600; color: #333; margin-bottom: 4px; }
        .card-desc { font-size: 12px; color: #999; line-height: 1.5; }
        .footer-note {
            text-align: center; margin-top: 40px; font-size: 12px; color: #aaa;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="main-title">{替换为架构标题}</div>
        <!-- 终端接入层 -->
        <div class="layer layer-terminal">
            <div class="layer-title" style="color:#2e7d32;">终端/接入层</div>
            <div class="cards">
                <!-- 替换自定义模块 -->
                <div class="card"><div class="card-title">模块名称</div><div class="card-desc">模块功能简述</div></div>
            </div>
        </div>
        <!-- 核心业务应用层 -->
        <div class="layer layer-business">
            <div class="layer-title" style="color:#1565c0;">核心业务应用层</div>
            <div class="cards">
                <!-- 替换自定义模块 -->
            </div>
        </div>
        <!-- 中台能力层 -->
        <div class="layer layer-middleware">
            <div class="layer-title" style="color:#7b1fa2;">公共中台能力层</div>
            <div class="cards">
                <!-- 替换自定义模块 -->
            </div>
        </div>
        <!-- 底层底座层 -->
        <div class="layer layer-infra">
            <div class="layer-title" style="color:#e65100;">基础技术底座层</div>
            <div class="cards">
                <!-- 替换自定义模块 -->
            </div>
        </div>
        <div class="footer-note">基于公开行业信息梳理的通用宏观架构</div>
    </div>
</body>
</html>
```

## 模板2：微服务Grid网格科技风（用户要求后端技术架构时使用）
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>微服务架构图</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; padding: 40px 20px;
        }
        .container { max-width: 1400px; margin:0 auto; background: rgba(255,255,255,0.95); border-radius: 16px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        h1 { text-align: center; color: #333; margin-bottom: 40px; font-size: 36px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }
        .service {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff; border-radius: 12px; padding: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15); transition: transform 0.3s;
        }
        .service:hover { transform: translateY(-5px); }
        .service h3 { font-size: 18px; margin-bottom: 8px; }
        .service p { font-size: 13px; opacity: 0.9; }
        .gateway { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .db { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
    </style>
</head>
<body>
    <div class="container">
        <h1>微服务系统架构图</h1>
        <div class="grid">
            <div class="service gateway"><h3>API Gateway</h3><p>负载均衡、路由、限流熔断</p></div>
            <!-- 自定义业务服务模块 -->
            <div class="service db"><h3>数据存储集群</h3><p>MySQL、Redis、分库分表</p></div>
        </div>
    </div>
</body>
</html>
```
