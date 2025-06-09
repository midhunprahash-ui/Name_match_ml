from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
from thefuzz import fuzz
import jellyfish
import re
import os

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compute_match_score(username, full_name, first_name, last_name, emp_id):
    numbers_in_username = re.findall(r'\d+', username)
    number_match_bonus = 0
    if numbers_in_username:
        if str(emp_id) in numbers_in_username:
            number_match_bonus = 14

    lev_full = fuzz.ratio(username, full_name)
    partial_full = fuzz.partial_ratio(username, full_name)
    token_set_full = fuzz.token_set_ratio(username, full_name)

    lev_first = fuzz.ratio(username, first_name)
    partial_first = fuzz.partial_ratio(username, first_name)
    token_set_first = fuzz.token_set_ratio(username, first_name)

    lev_last = fuzz.ratio(username, last_name)
    partial_last = fuzz.partial_ratio(username, last_name)
    token_set_last = fuzz.token_set_ratio(username, last_name)

    soundex_match_last = int(jellyfish.soundex(username) == jellyfish.soundex(last_name))
    metaphone_match_last = int(jellyfish.metaphone(username) == jellyfish.metaphone(last_name))
    soundex_match_first = int(jellyfish.soundex(username) == jellyfish.soundex(first_name))
    metaphone_match_first = int(jellyfish.metaphone(username) == jellyfish.metaphone(first_name))

    max_lev = max(lev_full, lev_first, lev_last)
    max_partial = max(partial_full, partial_first, partial_last)
    max_token_set = max(token_set_full, token_set_first, token_set_last)

    composite = (
        (max_lev * 0.4) +
        (max_partial * 0.3) +
        (max_token_set * 0.3) +
        (soundex_match_last * 10) +
        (metaphone_match_last * 10) +
        (soundex_match_first * 10) +
        (metaphone_match_first * 10) +
        number_match_bonus
    )
    return min(composite, 100)

def process_employees(df):
    df.columns = df.columns.str.lower()
    required_columns = {'emp_id', 'first_name', 'last_name'}
    if not required_columns.issubset(df.columns):
        missing_columns = required_columns - set(df.columns)
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
    df['first_name'] = df['first_name'].astype(str)
    df['last_name'] = df['last_name'].astype(str)
    df['employee_name'] = df['first_name'].str.strip() + ' ' + df['last_name'].str.strip()
    return df[['emp_id', 'employee_name', 'first_name', 'last_name']]

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            return render_template('upload.html', error='No file part')
        file = request.files['file']
        # If the user does not select a file, submit an empty part without filename
        if file.filename == '':
            return render_template('upload.html', error='No selected file')
        if file and allowed_file(file.filename):
            filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)
            return redirect(url_for('index', filename=filename))
        else:
            return render_template('upload.html', error='Invalid file type.  Only CSV files are allowed.')
    return render_template('upload.html')

@app.route('/index')
def index():
    filename = request.args.get('filename')
    if not filename:
        return "No file specified", 400

    try:
        employees = pd.read_csv(filename)
        employees = process_employees(employees)
    except ValueError as e:
        return render_template('error.html', error=str(e))
    except Exception as e:
        return render_template('error.html', error=f"Error reading or processing CSV: {str(e)}")

    matches = []
    top_matches = []
    input_username = ""

    if request.args.get('username'):
        input_username = request.args.get('username').strip().lower()

        employees['score'] = employees.apply(
            lambda row: compute_match_score(
                input_username,
                row['employee_name'].lower(),
                row['first_name'].lower(),
                row['last_name'].lower(),
                row['emp_id']
            ), axis=1
        )
        matches_df = employees[employees['score'] >= 65].sort_values('score', ascending=False)
        excluded_ids = set(matches_df['emp_id'])
        top_matches_df = employees[~employees['emp_id'].isin(excluded_ids].sort_values('score', ascending=False).head(5)

        matches = matches_df.to_dict(orient='records')
        top_matches = top_matches_df.to_dict(orient='records')
    return render_template(
        'index.html',
        matches=matches,
        top_matches=top_matches,
        input_username=input_username
    )

if __name__ == '__main__':
    app.run(debug=True)
