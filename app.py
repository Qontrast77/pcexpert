"""Веб-интерфейс экспертной системы (Flask)."""
from flask import Flask, jsonify, render_template, request

from expert import recommend, recommend_two, PART_TITLES
from knowledge_base import kb, TASK_NAMES, rub

app = Flask(__name__)
app.jinja_env.filters["rub"] = rub
app.jinja_env.globals["nrules"] = len(kb.rules)


@app.get("/")
def index():
    return render_template("index.html", tasks=TASK_NAMES, form={}, res=None)


@app.post("/")
def submit():
    form = request.form.to_dict()
    form["tasks"] = request.form.getlist("tasks")
    res = recommend_two(form)
    return render_template("index.html", tasks=TASK_NAMES, form=form, res=res,
                           part_titles=PART_TITLES)


@app.post("/api/recommend")
def api():
    res = recommend_two(request.get_json(force=True))
    for key in ("ideal", "local"):
        if res[key]:
            res[key].pop("engine", None)
    return jsonify(res)


@app.get("/rules")
def rules():
    groups = {}
    for r in kb.rules:
        groups.setdefault(r.group, []).append(r)
    return render_template("rules.html", groups=groups, total=len(kb.rules))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
