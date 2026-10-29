"""
简单的轨迹标注 Web 界面

运行方式：
    python scripts/annotation_ui.py

然后访问：http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitoring.postgres_trajectory_store import PostgresTrajectoryStore
from src.monitoring.active_learning import select_for_annotation

app = Flask(__name__)
store = PostgresTrajectoryStore()

# 当前标注会话的样本列表
current_batch = []
current_index = 0


@app.route('/')
def index():
    """首页：显示统计信息"""
    stats = store.get_stats()
    return render_template('index.html', stats=stats)


@app.route('/start_annotation', methods=['POST'])
def start_annotation():
    """开始标注会话：选择一批样本"""
    global current_batch, current_index

    budget = request.json.get('budget', 20)
    strategy = request.json.get('strategy', 'mixed')

    # 主动学习选择样本
    current_batch = select_for_annotation(store, budget=budget, strategy=strategy)
    current_index = 0

    return jsonify({
        'success': True,
        'total': len(current_batch),
        'message': f'已选择 {len(current_batch)} 个样本进行标注'
    })


@app.route('/next_sample', methods=['GET'])
def next_sample():
    """获取下一个待标注样本"""
    global current_batch, current_index

    if current_index >= len(current_batch):
        return jsonify({'finished': True})

    sample = current_batch[current_index]

    return jsonify({
        'finished': False,
        'progress': {
            'current': current_index + 1,
            'total': len(current_batch)
        },
        'sample': {
            'trajectory_id': sample['trajectory_id'],
            'task_description': sample['task_description'],
            'task_type': sample['task_type'],
            'mode': sample['mode'],
            'subtasks': sample.get('subtasks', []),
            'tool_calls': sample.get('tool_calls', []),
            'final_result': sample.get('final_result', ''),
            'success': sample.get('success', False),
            'execution_time': sample.get('execution_time', 0),
        }
    })


@app.route('/submit_annotation', methods=['POST'])
def submit_annotation():
    """提交标注"""
    global current_index

    data = request.json
    trajectory_id = data['trajectory_id']

    annotation = {
        'subtasks_quality': data.get('subtasks_quality'),
        'subtasks_feedback': data.get('subtasks_feedback', ''),
        'subtasks_corrected': data.get('subtasks_corrected', []),
        'tool_choices': data.get('tool_choices', []),
        'priority_ranking': data.get('priority_ranking', []),
        'overall_quality': data.get('overall_quality'),
        'comments': data.get('comments', ''),
    }

    # 保存标注
    store.save_annotation(trajectory_id, annotation, annotator='human')

    # 移动到下一个样本
    current_index += 1

    return jsonify({'success': True})


@app.route('/skip_sample', methods=['POST'])
def skip_sample():
    """跳过当前样本"""
    global current_index
    current_index += 1
    return jsonify({'success': True})


if __name__ == '__main__':
    # 创建模板目录
    templates_dir = Path(__file__).parent / 'templates'
    templates_dir.mkdir(exist_ok=True)

    # 创建简单的 HTML 模板
    index_html = templates_dir / 'index.html'
    if not index_html.exists():
        index_html.write_text('''<!DOCTYPE html>
<html>
<head>
    <title>轨迹标注系统</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 40px auto; padding: 20px; }
        .stats { background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 30px; }
        .stat-item { display: inline-block; margin-right: 30px; }
        .stat-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .stat-label { font-size: 14px; color: #7f8c8d; }
        button { background: #3498db; color: white; border: none; padding: 12px 24px;
                 border-radius: 4px; cursor: pointer; font-size: 16px; }
        button:hover { background: #2980b9; }
        .sample-card { border: 1px solid #ddd; padding: 20px; margin-bottom: 20px; border-radius: 8px; }
        .subtask { background: #ecf0f1; padding: 10px; margin: 5px 0; border-radius: 4px; }
        textarea { width: 100%; min-height: 80px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        .rating { display: flex; gap: 10px; margin: 10px 0; }
        .rating button { padding: 8px 16px; background: #95a5a6; }
        .rating button.active { background: #27ae60; }
        #progress { margin: 20px 0; font-size: 18px; color: #2c3e50; }
    </style>
</head>
<body>
    <h1>🎯 Agent 轨迹标注系统</h1>

    <div class="stats">
        <div class="stat-item">
            <div class="stat-value">{{ stats.total }}</div>
            <div class="stat-label">总轨迹数</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">{{ stats.pending }}</div>
            <div class="stat-label">待标注</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">{{ stats.annotated }}</div>
            <div class="stat-label">已标注</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">{{ "%.1f"|format(stats.successful * 100 / stats.total if stats.total > 0 else 0) }}%</div>
            <div class="stat-label">成功率</div>
        </div>
    </div>

    <div id="start-section">
        <h2>开始标注</h2>
        <p>选择标注策略和数量：</p>
        <select id="strategy">
            <option value="mixed">混合策略（推荐）</option>
            <option value="uncertainty">不确定性采样</option>
            <option value="diversity">多样性采样</option>
        </select>
        <input type="number" id="budget" value="20" min="5" max="100">
        <button onclick="startAnnotation()">开始标注</button>
    </div>

    <div id="annotation-section" style="display:none;">
        <div id="progress"></div>
        <div id="sample-container"></div>

        <div style="margin-top: 20px;">
            <h3>标注内容</h3>

            <label>任务分解质量（1-5）：</label>
            <div class="rating" id="subtasks-quality">
                <button onclick="setRating('subtasks', 1)">1</button>
                <button onclick="setRating('subtasks', 2)">2</button>
                <button onclick="setRating('subtasks', 3)">3</button>
                <button onclick="setRating('subtasks', 4)">4</button>
                <button onclick="setRating('subtasks', 5)">5</button>
            </div>

            <label>改进建议：</label>
            <textarea id="subtasks-feedback" placeholder="如何改进任务分解？"></textarea>

            <label>整体质量（1-5）：</label>
            <div class="rating" id="overall-quality">
                <button onclick="setRating('overall', 1)">1</button>
                <button onclick="setRating('overall', 2)">2</button>
                <button onclick="setRating('overall', 3)">3</button>
                <button onclick="setRating('overall', 4)">4</button>
                <button onclick="setRating('overall', 5)">5</button>
            </div>

            <label>备注：</label>
            <textarea id="comments" placeholder="其他评论"></textarea>

            <div style="margin-top: 20px;">
                <button onclick="submitAnnotation()">提交标注</button>
                <button onclick="skipSample()" style="background: #95a5a6;">跳过</button>
            </div>
        </div>
    </div>

    <script>
        let currentSample = null;
        let ratings = { subtasks: 0, overall: 0 };

        function startAnnotation() {
            const strategy = document.getElementById('strategy').value;
            const budget = parseInt(document.getElementById('budget').value);

            fetch('/start_annotation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ strategy, budget })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('start-section').style.display = 'none';
                    document.getElementById('annotation-section').style.display = 'block';
                    loadNextSample();
                }
            });
        }

        function loadNextSample() {
            fetch('/next_sample')
            .then(r => r.json())
            .then(data => {
                if (data.finished) {
                    alert('标注完成！');
                    location.reload();
                    return;
                }

                currentSample = data.sample;
                document.getElementById('progress').innerText =
                    `进度：${data.progress.current} / ${data.progress.total}`;

                const html = `
                    <div class="sample-card">
                        <h3>任务描述</h3>
                        <p>${currentSample.task_description}</p>

                        <p><strong>类型：</strong>${currentSample.task_type} |
                           <strong>模式：</strong>${currentSample.mode} |
                           <strong>耗时：</strong>${currentSample.execution_time.toFixed(2)}s |
                           <strong>成功：</strong>${currentSample.success ? '✅' : '❌'}</p>

                        <h4>子任务分解（${currentSample.subtasks.length} 个）</h4>
                        ${currentSample.subtasks.map((s, i) =>
                            `<div class="subtask">${i+1}. ${s}</div>`
                        ).join('')}

                        <h4>最终结果</h4>
                        <p>${currentSample.final_result || '（无结果）'}</p>
                    </div>
                `;

                document.getElementById('sample-container').innerHTML = html;

                // 重置表单
                ratings = { subtasks: 0, overall: 0 };
                document.querySelectorAll('.rating button').forEach(b => b.classList.remove('active'));
                document.getElementById('subtasks-feedback').value = '';
                document.getElementById('comments').value = '';
            });
        }

        function setRating(type, value) {
            ratings[type] = value;
            const container = document.getElementById(`${type}-quality`);
            container.querySelectorAll('button').forEach((b, i) => {
                b.classList.toggle('active', i < value);
            });
        }

        function submitAnnotation() {
            if (ratings.subtasks === 0 || ratings.overall === 0) {
                alert('请完成所有评分');
                return;
            }

            const annotation = {
                trajectory_id: currentSample.trajectory_id,
                subtasks_quality: ratings.subtasks,
                subtasks_feedback: document.getElementById('subtasks-feedback').value,
                overall_quality: ratings.overall,
                comments: document.getElementById('comments').value,
            };

            fetch('/submit_annotation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(annotation)
            })
            .then(r => r.json())
            .then(() => loadNextSample());
        }

        function skipSample() {
            fetch('/skip_sample', { method: 'POST' })
            .then(() => loadNextSample());
        }
    </script>
</body>
</html>''', encoding='utf-8')

    print('✅ 标注界面启动')
    print('📍 访问：http://localhost:5000')
    app.run(debug=True, port=5000)
