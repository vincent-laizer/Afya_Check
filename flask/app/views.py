from time import sleep
from app import app, db
from flask import render_template, flash, request, redirect, url_for, jsonify, Response, stream_with_context
from flask_login import login_user, logout_user, current_user, login_required
from app.schema import User, CheckIn, Assessment, AssessmentOption, AssessmentQuestion
from app.utils import (
    create_gauge_chart, get_predicted_condition, get_recommended_assessment, 
    age_group_from_age, get_gpt3_response, initialize_openai, gpt_response_to_html
)

@app.route('/')
@app.route('/home')
def index():
    return render_template('index.html', title='Welcome')

@app.route('/check-in', methods=['GET', 'POST'])
def check_in():
    if request.method == "GET":
        items = []
        ci = CheckIn.query.all()
        for c in ci:
            items.append(c.to_dict())
        return render_template('checkin.html', title='Early Check-In', items=items)
    
    # post method
    data = request.form
    age = data.get("age")
    gender = data.get("gender")
    symptoms = data.getlist("symptoms")

    if current_user.is_authenticated:
        age = current_user.age
        gender = current_user.gender

    if int(age) < 13:
        return jsonify({"error": "You must be at least 13 years old to register"})
    
    if len(symptoms) < 1:
        return jsonify({"error": "You must select at least one symptom"})

    selected_language = "English"
    predicted_condition = get_predicted_condition(age, gender, selected_language, symptoms)
    recommended_assessments = get_recommended_assessment(predicted_condition)
    return jsonify(recommended_assessments)

@app.route('/assessments')
def assessments():
    ass = [
        "ADHD", "Alcohol", "Anxiety", "Bipolar", "Depression",
        "Dementia", "Drug", "OCD", "PSQ", "PTSD"
    ]
    return render_template('assessments.html', title='Assessment', ass=ass)

@app.route('/assessment/<string:option>')
def assessment(option):
    ass = Assessment.query.filter(Assessment.title.like(f"%{option}%")).first()
    return render_template('assessment.html', title=f"{option} Assessment", ass=ass)

@app.route('/results', methods=["POST"])
@stream_with_context
def results():
    data = request.form
    age_group = data.get("age")
    gender = data.get("gender")
    title = data.get("title")

    if current_user.is_authenticated:
        age_group = age_group_from_age(current_user.age)
        gender = current_user.gender

    score = 0
    ass = Assessment.query.filter(Assessment.title.like(f"%{title}%")).first().to_dict()
    questions = ass["questions"]

    for qn in questions:
        score += int(data.get(f"id_{qn['id']}"))

    result_text = "Your score suggests Minimal issues"

    gpt3_prompt = f"You are a help full assistant"
    gpt3_prompt = f'''gpt3_prompt = f"""
        As a knowledgeable mental health assistant:
        I have completed the bipolar assessment, scoring {score} out of {ass['max_score']}, indicating: '{result_text}'.
        1. Provide an empathetic response based on my  score and tell me if my score is high or low.
        2. Define bipolar disorder in a broader scope.
        3. List negative symptoms of bipolar disorder and explain how it affects daily life.
        4. Offer insights and coping strategies and natural ways for managing bipolar disorder.
        5. Commend me for undertaking the assessment.
        6. If my score is high encourage me to go to the hospital.
        """
        gpt3_response = get_gpt3_response(gpt3_prompt, selected_language)
        '''
    
    def generate_content():
        # Initially, send the loading page HTML
        yield render_template(
            'results.html', 
            title="Assessment Score", 
            res=None,
            plot=create_gauge_chart(score, max_score=ass["max_score"], assessment_name="")
        )

        initialize_openai()
        # gpt3_response = get_gpt3_response(gpt3_prompt)
        # gpt_text = gpt_response_to_html(gpt3_response)
        sleep(2)

        yield f'<div class="text my-2 col-lg-6 mx-auto"> \
               {"gpt_text"} \
            </div>'
        yield '<div class="text text-green my-3 col-lg-6 mx-auto"> \
                <p>\
                    <strong>Reminder: </strong> \
                    These insights are based on the provided conversation and are for informational \
                    purposes only. They are not a definitive diagnosis. Please consult with a healthcare \
                    professional for a comprehensive assessment. \
                </p> \
            </div>'

    return Response(generate_content(), content_type='text/html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == "GET":
        return render_template('register.html', title='Register')
    
    # post method
    username = request.form.get("username").strip()
    age = request.form.get("age")
    gender = request.form.get("gender")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")

    if password != confirm_password:
        flash("Passwords do not match")
        return render_template('register.html', title='Register')
    
    user = User.query.filter_by(username=username).first()
    if user:
        flash(f"The username {user.username} already exists")
        return render_template('register.html', title='Register')
    
    if len(username) < 4:
        flash("Username must be at least 4 characters")
        return render_template('register.html', title='Register')
    
    if len(password) < 6:
        flash("Password must be at least 6 characters")
        return render_template('register.html', title='Register')
    
    if int(age) < 13:
        flash("You must be at least 13 years old to register")
        return render_template('register.html', title='Register')
    
    user = User(username=username, age=age, gender=gender, password=password)
    db.session.add(user)
    db.session.commit()
    
    flash(f"Welcome, {username}. Please login to continue.")
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == "GET":
        return render_template('login.html', title='Login')
    
    # post method
    username = request.form.get("username").strip()
    password = request.form.get("password")
    user = User.query.filter_by(username=username).first()

    if user and user.password == password:
        login_user(user)
        return render_template('index.html', title='Welcome')
    else:
        flash("Incorrect username or password")
        return render_template('login.html', title='Login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/scores')
@login_required
def scores():
    return render_template('scores.html', title='Scores')
