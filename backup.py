from flask import Flask, render_template, request, flash, redirect, url_for, send_file
import pandas as pd
from thefuzz import fuzz
import jellyfish
import re
import os
import io

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

NUM_TOP_GROUP_MATCHES = 2
NUM_ADDITIONAL_POSSIBLE_MATCHES = 2
TOTAL_MATCHES_TO_DISPLAY = NUM_TOP_GROUP_MATCHES + NUM_ADDITIONAL_POSSIBLE_MATCHES
SCORE_THRESHOLD = 50


def compute_match_score(username, employee_name, first_name, last_name, emp_id):
    username_lower = str(username).lower().strip()
    employee_name_lower = str(employee_name).lower().strip()
    first_name_lower = str(first_name).lower().strip()
    last_name_lower = str(last_name).lower().strip()
    emp_id_str = str(emp_id).lower().strip()

    username_parts = re.split(r'[\._\-\s]', username_lower)
    part1 = username_parts[0] if len(username_parts) > 0 else ''
    part2 = username_parts[1] if len(username_parts) > 1 else ''

    possible_patterns = [
        f"{first_name_lower}.{last_name_lower}",
        f"{last_name_lower}.{first_name_lower}",
        f"{first_name_lower}_{last_name_lower}",
        f"{last_name_lower}_{first_name_lower}",
        f"{first_name_lower}{last_name_lower}",
        f"{last_name_lower}{first_name_lower}",
        f"{first_name_lower} {last_name_lower}",
        f"{last_name_lower} {first_name_lower}"
    ]
    if username_lower in possible_patterns:
        return 100.0

    split_bonus = 0
    if ((part1 == first_name_lower and part2 == last_name_lower) or
        (part2 == first_name_lower and part1 == last_name_lower)):
        split_bonus += 10

    number_match_bonus = 0 if emp_id_str in username_lower else 0

    lev_full = fuzz.ratio(username_lower, employee_name_lower)
    partial_full = fuzz.partial_ratio(username_lower, employee_name_lower)
    token_set_full = fuzz.token_set_ratio(username_lower, employee_name_lower)

    token_set_first = fuzz.token_set_ratio(username_lower, first_name_lower)
    token_set_last = fuzz.token_set_ratio(username_lower, last_name_lower)

    soundex_match_last = int(jellyfish.soundex(username_lower) == jellyfish.soundex(last_name_lower))
    metaphone_match_last = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(last_name_lower))
    soundex_match_first = int(jellyfish.soundex(username_lower) == jellyfish.soundex(first_name_lower))
    metaphone_match_first = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(first_name_lower))

    initial_bonus = 0
    if username_lower[0] == first_name_lower[0]:
        initial_bonus += 5
    if '.' in username_lower:
        parts = username_lower.split('.')
        if len(parts) > 1 and parts[1][0] == first_name_lower[0]:
            initial_bonus += 5

    composite = (
        (lev_full * 0.2) +
        (partial_full * 0.2) +
        (token_set_full * 0.2) +
        (token_set_last * 0.3) +
        (token_set_first * 0.2) +
        (soundex_match_last * 6) +
        (metaphone_match_last * 7) +
        (soundex_match_first * 3) +
        (metaphone_match_first * 3) +
        split_bonus +
        initial_bonus +
        number_match_bonus
    )
    return min(composite, 100)


def fetch_employees(csv_file_buffer):
    CANONICAL_COLUMN_ALIASES = {
        'emp_id': ['employee_id', 'employee id', 'id_employee', 'staff_id', 'emp id', 'empid', 'id', 'employee no', 'emp no'],
        'first_name': ['first name', 'fname', 'given_name', 'first', 'f_name', 'name (first)', 'namefirst'],
        'last_name': ['last name', 'lname', 'surname', 'family_name', 'l_name', 'name (last)', 'namelast'],
        'employee_name': ['full name', 'fullname', 'emp_name', 'name of employee', 'name']
    }

    try:
        df = pd.read_csv(csv_file_buffer)
        df.columns = df.columns.str.lower()

        for canonical_name, aliases in CANONICAL_COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in df.columns and alias != canonical_name:
                    df.rename(columns={alias: canonical_name}, inplace=True)
                    break

        if 'employee_name' not in df.columns and ('first_name' in df.columns or 'last_name' in df.columns):
            df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
            df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
            df['employee_name'] = df['first_name'] + ' ' + df['last_name']
        elif 'employee_name' in df.columns:
            df['employee_name'] = df['employee_name'].astype(str).str.strip()
            if 'first_name' not in df.columns and 'last_name' not in df.columns:
                name_parts = df['employee_name'].str.split(n=1, expand=True)
                df['first_name'] = name_parts[0].fillna('').str.strip()
                df['last_name'] = name_parts[1].fillna('') if len(name_parts.columns) > 1 else ''
        elif 'first_name' in df.columns and 'last_name' in df.columns:
            df['employee_name'] = df['first_name'] + ' ' + df['last_name']

        df['emp_id'] = df['emp_id'].astype(str).str.strip()
        df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
        df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
        df['employee_name'] = df['employee_name'].fillna('').astype(str).str.strip()

        return df[['emp_id', 'first_name', 'last_name', 'employee_name']]

    except Exception as e:
        flash(f"Error processing employee data: {e}", "error")
        return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        employee_csv = request.files.get('employee_csv_file')
        usernames_csv = request.files.get('usernames_csv_file')

        if not employee_csv or not usernames_csv:
            flash("Upload both employee and username CSVs.", "error")
            return redirect(url_for('index'))

        employees_df = fetch_employees(employee_csv)
        if employees_df.empty:
            return redirect(url_for('index'))

        try:
            usernames_df = pd.read_csv(usernames_csv)
            usernames_df.columns = usernames_df.columns.str.lower()
            if 'username' not in usernames_df.columns:
                flash("Usernames CSV must contain 'username' column.", "error")
                return redirect(url_for('index'))
            input_usernames = usernames_df['username'].astype(str).tolist()
        except Exception as e:
            flash(f"Error reading usernames CSV: {e}", "error")
            return redirect(url_for('index'))

        final_output = []

        for uname in input_usernames:
            employees_df['score'] = employees_df.apply(
                lambda row: compute_match_score(uname, row['employee_name'], row['first_name'], row['last_name'], row['emp_id']),
                axis=1
            )

            top_matches = employees_df.sort_values('score', ascending=False).head(TOTAL_MATCHES_TO_DISPLAY)
            valid_matches = top_matches[top_matches['score'] >= SCORE_THRESHOLD]

            if valid_matches.empty:
                final_output.append({
                    'username': uname,
                    'emp_id': 'N/A',
                    'emp_name': 'USER NOT FOUND',
                    'confidence_score': '0.00%',
                    'match_type': 'USER NOT FOUND'
                })
            else:
                labels_by_rank = {
                    1: "HIGH CONFIDENCE",
                    2: "2nd HIGH CONFIDENCE",
                    3: "3rd HIGH CONFIDENCE",
                    4: "NOT SURE"
                }

                ranked_matches = []
                current_rank = 1
                prev_score = None

                for _, row in valid_matches.iterrows():
                    score = row['score']
                    if prev_score is not None and score < prev_score:
                        current_rank += 1
                    label = labels_by_rank.get(current_rank, "")
                    ranked_matches.append((row, label))
                    prev_score = score

                for match, label in ranked_matches:
                    final_output.append({
                        'username': uname,
                        'emp_id': match['emp_id'],
                        'emp_name': match['employee_name'],
                        'confidence_score': f"{match['score']:.2f}%",
                        'match_type': label
                    })

                final_output.append({'username': '', 'emp_id': '', 'emp_name': '', 'confidence_score': '', 'match_type': ''})

        output_df = pd.DataFrame(final_output)
        output_buffer = io.StringIO()
        output_df.to_csv(output_buffer, index=False)
        output_buffer.seek(0)

        return send_file(
            io.BytesIO(output_buffer.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='username_matches.csv'
        )

    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)
