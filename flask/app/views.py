import csv
from io import StringIO
from time import sleep
from datetime import datetime, timedelta
from app import app, db
from flask import (
    render_template, flash, request, redirect, url_for, jsonify, Response, 
    stream_with_context, session
)
from flask_login import login_user, logout_user, current_user, login_required
from app.schema import User, CheckIn, Assessment, UserScores
from app.utils import (
    create_gauge_chart, get_predicted_condition, get_recommended_assessment, 
    age_group_from_age, get_gpt3_response, initialize_openai, gpt_response_to_html,
    create_gpt_prompt, create_result_text
)

@app.route('/')
@app.route('/home')
def index():
    if session.get("lang") is None:
        session["lang"] = "en"

    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin"))
    
    title = "Welcome"
    if session["lang"] == "sw":
        title = "Karibu"
    
    return render_template('index.html', title=title)

@app.route('/lang/<string:lang>')
def lang(lang):
    session['lang'] = lang
    return jsonify({"status": "success", "lang": session['lang']})

@app.route('/check-in', methods=['GET', 'POST'])
def check_in():
    if session.get("lang") is None:
        session["lang"] = "en"

    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin"))

    title = "Early Check-In"
    if session["lang"] == "sw":
        title = "Tathmini ya Awali"
    
    if request.method == "GET":
        items = []
        ci = CheckIn.query.all()
        for c in ci:
            items.append(c.to_dict())
        return render_template('checkin.html', title=title, items=items)
    
    # post method
    data = request.form
    age = data.get("age")
    gender = data.get("gender")
    symptoms = data.getlist("symptoms")

    if current_user.is_authenticated:
        age = current_user.age
        gender = current_user.gender

    if int(age) < 13:
        if session["lang"] == "sw":
            return jsonify({"error": "Lazima uwe na angalau miaka 13 kujisajili"})
        return jsonify({"error": "You must be at least 13 years old to register"})
    
    if len(symptoms) < 1:
        if session["lang"] == "sw":
            return jsonify({"error": "Chagua angalau dalili moja"})   
        return jsonify({"error": "You must select at least one symptom"})

    selected_language = "English"

 
    predicted_condition = get_predicted_condition(age, gender, selected_language, symptoms)
    recommended_assessments = get_recommended_assessment(predicted_condition)
    return jsonify(recommended_assessments)

@app.route('/assessments')
def assessments():
    if session.get("lang") is None:
        session["lang"] = "en"

    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin"))

    title = "Assessment"
    if session["lang"] == "sw":
        title = "Tathmini"
    
    ass = [
        "ADHD", "Alcohol", "Anxiety", "Bipolar", "Depression",
        "Dementia", "Drug", "OCD", "PSQ", "PTSD",
    ]
    return render_template('assessments.html', title=title, ass=ass)

@app.route('/assessment/<string:option>')
def assessment(option):
    if session.get("lang") is None:
        session["lang"] = "en"

    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin"))
    
    title = f"{option} Assessment"
    ass = None
    if session["lang"] == "sw":
        title = f"Tathmini ya {option}"
        ass = Assessment.query.filter(Assessment.title_sw.like(f"%{option}%")).first()
    else:
        title = title = f"{option} Assessment"
        ass = Assessment.query.filter(Assessment.title.like(f"%{option}%")).first()

    return render_template('assessment.html', title=title, ass=ass)

@app.route('/results', methods=["POST"])
@stream_with_context
def results():
    if session.get("lang") is None:
        session["lang"] = "en"
    
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin"))

    data = request.form
    age_group = data.get("age")
    gender = data.get("gender")
    title = data.get("title")

    if current_user.is_authenticated:
        age_group = age_group_from_age(current_user.age)
        gender = current_user.gender

    score = 0
    ass = None

    if session["lang"] == "sw":
        ass = Assessment.query.filter(Assessment.title_sw.like(f"%{title}%")).first().to_dict()
    else:
        ass = Assessment.query.filter(Assessment.title.like(f"%{title}%")).first().to_dict()

    questions = ass["questions"]
    for qn in questions:
        score += int(data.get(f"id_{qn['id']}"))

    language = "English"
    if session["lang"] == "sw":
        language = "Swahili"

    result_text = create_result_text(ass, score, selected_language=language)

    gpt3_prompt = f"You are a help full assistant"
    gpt3_prompt = create_gpt_prompt(ass, score, result_text, selected_language=language)
    
    def generate_content():
        # Initially, send html page
        yield render_template(
            'results.html', 
            title="Majibu ya Tathmini" if session["lang"]=="sw" else "Assessment Score", 
            res={"title": ass["title"], "result_text": result_text},
            plot=create_gauge_chart(
                score, 
                max_score=ass["max_score"], 
                assessment_name="",
                selected_language=language
            )
        )

        initialize_openai()
        # TODO: uncomment gpt api calls in production env, now commented in order
        # to save api calls, emulate gpt response with 3 seconds sleep
        # sleep(3)
        # gpt_text = "placeholder text"
        gpt3_response = get_gpt3_response(gpt3_prompt, language=language)
        gpt_text = gpt_response_to_html(gpt3_response)

        # Finally: send gpt response
        yield f'<div class="text my-2 col-lg-6 mx-auto"> \
               {gpt_text} \
            </div>'
        yield '<div class="text text-green my-3 col-lg-6 mx-auto"> \
                <p>\
                <strong>Kumbusho: </strong> \
                    Kumbuka kwamba mazungumzo yaliyotolewa na ni kwa madhumuni ya taarifa pekee. \
                    Hayawakilishi utambuzi wala tathmini kamili ya kitabibu. Tafadhali shauriana na \
                    mtaalamu wa afya kwa tathmini kamili \
                </p> \
            </div>\
        ' if session["lang"] == "sw" else '<div class="text text-green my-3 col-lg-6 mx-auto"> \
                <p>\
                    <strong>Reminder: </strong> \
                    These insights are based on the provided conversation and are for informational \
                    purposes only. They are not a definitive diagnosis. Please consult with a healthcare \
                    professional for a comprehensive assessment. \
                </p> \
            </div>'

    # save score in db
    user_id = None
    if current_user.is_authenticated:
        user_id = current_user.id

    us = UserScores(
        user_id=user_id, 
        assessment_id=ass["id"], 
        score=score, 
        age_group=age_group, 
        gender=gender)
    db.session.add(us)
    db.session.commit()    

    return Response(generate_content(), content_type='text/html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if session.get("lang") is None:
        session["lang"] = "en"
    
    title = "Register"
    if session["lang"] == "sw":
        title = "Jisajili"
    
    if request.method == "GET":
        return render_template('register.html', title=title)
    
    # post method
    username = request.form.get("username").strip()
    age = request.form.get("age")
    gender = request.form.get("gender")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")

    if password != confirm_password:
        if session["lang"] == "sw":
            flash("Nenosiri halifanani")
        else:
            flash("Passwords do not match")
        return render_template('register.html', title=title)
    
    user = User.query.filter_by(username=username).first()
    if user:
        if session["lang"] == "sw":
            flash(f"Jina la mtumiaji {user.username} tayari lipo")
        else:
            flash(f"The username {user.username} already exists")
        return render_template('register.html', title=title)
    
    if len(username) < 4:
        if session["lang"] == "sw":
            flash("Jina la mtumiaji liwe na angalau herufi 4")
        else:
            flash("Username must be at least 4 characters")
        return render_template('register.html', title=title)
    
    if len(password) < 6:
        if session["lang"] == "sw":
            flash("Nenosiri liwe na herufi angalau 6")
        else:
            flash("Password must be at least 6 characters")
        return render_template('register.html', title=title)
    
    if int(age) < 13:
        if session["lang"] == "sw":
            flash("Lazima uwe angalau na miaka 13 kujisajili")
        else:
            flash("You must be at least 13 years old to register")
        return render_template('register.html', title=title)
    
    user = User(username=username, age=age, gender=gender, password=password)
    db.session.add(user)
    db.session.commit()
    
    if session["lang"] == "sw":
        flash(f"Karibu, {username}. Tafadhali ingia kudendelea.")
    else:
        flash(f"Welcome, {username}. Please login to continue.")
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if session.get("lang") is None:
        session["lang"] = "en"
    
    title = "Login"
    if session["lang"] == "sw":
        title = "Ingia"
    
    if request.method == "GET":
        return render_template('login.html', title=title)
    
    # post method
    username = request.form.get("username").strip()
    password = request.form.get("password")
    user = User.query.filter_by(username=username).first()

    if user and user.password == password:
        login_user(user)
        if user.role == "admin":
            return redirect(url_for("admin"))
        return redirect(url_for("index"))
    else:
        if session["lang"] == "sw":
            flash("Jina la mtumiaji au Nenosiri sio sahihi")
        else:
            flash("Incorrect username or password")
        return redirect(url_for("login"))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/scores')
@login_required
def scores():
    if session.get("lang") is None:
        session["lang"] = "en"

    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin"))
    
    title = "Scores"
    if session["lang"] == "sw":
        title = "Majibu"
    
    scores = UserScores.query.filter_by(user_id=current_user.id).order_by(UserScores.date_taken.desc()).all()
    return render_template('scores.html', title=title, scores=scores)


@app.route('/admin')
@login_required
def admin():
    if session.get("lang") is None:
        session["lang"] = "en"
    
    title = "Admin"
    if session["lang"] == "sw":
        title = "Msimamizi"
    
    if current_user.role != "admin":
        return redirect(url_for("index"))
    
    users = User.query.all()
    user_count = len(users)
    return render_template("admin/index.html", users=users, user_count=user_count)

@app.route('/admin/scores')
@login_required
def admin_scores():
    if session.get("lang") is None:
        session["lang"] = "en"
    
    title = "Scores"
    if session["lang"] == "sw":
        title = "Majibu"
    
    if current_user.role != "admin":
        return redirect(url_for("index"))
    
    per_page = 10
    page = request.args.get("page", 1, type=int)
    std = request.args.get("start_date") or (datetime.now()-timedelta(weeks=1)).strftime("%Y-%m-%d")
    edt = request.args.get("end_date") or datetime.now().strftime("%Y-%m-%d")
    # paginate the scores
    pagination = UserScores.query.filter(
            UserScores.date_taken.between(std, edt)
        ).order_by(
            UserScores.date_taken.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
    scores = pagination.items
    return render_template(
        "admin/scores.html", scores=scores, pagination=pagination,
        start_date=std, end_date=edt)

@app.route('/admin/export')
@login_required
def admin_export():
    if session.get("lang") is None:
        session["lang"] = "en"
    
    title = "Export"
    if session["lang"] == "sw":
        title = "Hamisha"
    
    if current_user.role != "admin":
        return redirect(url_for("index"))
    
    std = request.args.get("start_date") or (datetime.now()-timedelta(weeks=1)).strftime("%Y-%m-%d")
    edt = request.args.get("end_date") or datetime.now().strftime("%Y-%m-%d")
    scores = UserScores.query.filter(
            UserScores.date_taken.between(std, edt)
        ).order_by(
            UserScores.date_taken.desc()
        ).all()
    
    data_list = []
    for score in scores:
        data_list.append({
            "Assessment Name": score.assessment.title,
            "User's Score": score.score,
            "Total Score": score.assessment.max_score,
            "Age Group": score.age_group,
            "Gender": score.gender,
            "Date Taken": score.date_taken.strftime("%Y-%m-%d %H:%M")
        })

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=data_list[0].keys())
    writer.writeheader()
    writer.writerows(data_list)

    output.seek(0)
    filename = f"{std} to {edt}.csv"
    return Response(
        output, mimetype="text/csv", 
        headers={"Content-Disposition":f"attachment;filename={filename}"})
