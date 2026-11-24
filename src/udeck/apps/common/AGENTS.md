# common/
> L2 | Parent: ../AGENTS.md

成员清单：

__init__.py: 共享应用包入口。
controller.py: 应用导航、Home 交接、扫描取消信号与退出契约；交接跳过库重建。
input.py: 显示前接管、单轮焦点确认和代次隔离释放；后台停止查询。
library.py: 媒体源扫描、内容类型与库条目读取。
model.py: 共享库列表的 Qt 增量模型。
state.py: 应用偏好、原子状态写入与源索引。
qml/: 应用外壳、短过渡、标题与封面视图。见该目录 AGENTS.md。

返回桌面发送 Home 请求和有限阶段计时。
交接不重建后台应用的列表状态。
桌面取得焦点后，应用留在后台。
返回过程不同时最小化应用。
取消扫描发出 scanCancelled，运行层撤销待打开文件。

[PROTOCOL]: Update this header on change, then check AGENTS.md
