import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sys

# --- Database Management Class ---

class DatabaseManager:
    """Handles all SQLite database connections and operations."""
    
    def __init__(self, db_name='library.db'):
        self.db_name = db_name
        self._initialize_db()

    def _get_connection(self):
        """Returns a connection object."""
        return sqlite3.connect(self.db_name, timeout=10) 

    def _initialize_db(self):
        """Creates the 'books' table if it doesn't exist and populates initial data."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    book_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    price REAL NOT NULL,
                    edition INTEGER NOT NULL
                )
            """)
            conn.commit()
            
            cursor.execute("SELECT COUNT(*) FROM books")
            if cursor.fetchone()[0] == 0:
                self._insert_initial_data(cursor)
                conn.commit()
                print("Database initialized with sample data.")

        except sqlite3.Error as e:
            print(f"SQLite error during initialization: {e}")
            sys.exit(1)
        finally:
            conn.close()

    def _insert_initial_data(self, cursor):
        """Inserts initial dummy data."""
        initial_books = [
            ('The C++ Programming Language', 'Computer Science', 750.00, 4),
            ('Calculus: Early Transcendentals', 'Mathematics', 980.50, 8),
            ('Introduction to Data Science', 'Computer Science', 620.00, 2),
            ('Linear Algebra and Its Applications', 'Mathematics', 850.00, 5),
            ('Organic Chemistry', 'Science', 1100.00, 10)
        ]
        cursor.executemany("""
            INSERT INTO books (name, subject, price, edition) 
            VALUES (?, ?, ?, ?)
        """, initial_books)

    def add_book(self, name, subject, price, edition):
        """Adds a new book."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO books (name, subject, price, edition) 
                VALUES (?, ?, ?, ?)
            """, (name, subject, price, edition))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Error adding book: {e}")
            return None
        finally:
            conn.close()

    def remove_book(self, book_id):
        """Removes a book by its ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM books WHERE book_id = ?", (book_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Error removing book: {e}")
            return False
        finally:
            conn.close()

    def get_all_books(self):
        """Retrieves all books as a list of dictionaries."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM books ORDER BY book_id DESC")
            books = [dict(row) for row in cursor.fetchall()]
            return books
        except sqlite3.Error as e:
            print(f"Error fetching books: {e}")
            return []
        finally:
            conn.close()

# --- Search & Recommendation Logic ---

def find_books(db_manager, query):
    """Searches books by name or subject using SQLite LIKE."""
    conn = db_manager._get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query_param = f'%{query.strip().lower()}%'
    
    try:
        cursor.execute("""
            SELECT * FROM books 
            WHERE LOWER(name) LIKE ? OR LOWER(subject) LIKE ?
        """, (query_param, query_param))
        
        results = [dict(row) for row in cursor.fetchall()]
        return results
    except sqlite3.Error as e:
        print(f"Search error: {e}")
        return []
    finally:
        conn.close()

def get_recommendations(db_manager, query, found_books):
    """Generates recommendations based on the query's subject."""
    query = query.strip().lower()
    target_subject = None
    
    # 1. Determine the target subject
    if found_books:
        target_subject = found_books[0]['subject']
    else:
        # Check if the query matches an existing subject name
        all_subjects = {book['subject'] for book in db_manager.get_all_books()}
        matched_subject = next((s for s in all_subjects if query in s.lower()), None)
        
        if not matched_subject:
            all_subjects_str = ", ".join(all_subjects) if all_subjects else "No subjects available."
            message = f"I couldn't find a direct match for '{query}'. Try searching one of these subjects: {all_subjects_str}"
            return message, []
        
        target_subject = matched_subject

    # 2. Retrieve all books of that subject
    conn = db_manager._get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM books WHERE subject = ?", (target_subject,))
        recommended_books = [
            dict(row) for row in cursor.fetchall()
            if dict(row)['name'].lower() != query
        ]
        
        message = f"💡 I didn't find that specific book, but since you are interested in **{target_subject}**, check out these related titles:"
        return message, recommended_books

    except sqlite3.Error as e:
        print(f"Recommendation error: {e}")
        return "Sorry, an error occurred while fetching recommendations.", []
    finally:
        conn.close()

# --- Flask App Initialization and Routes ---

app = Flask(__name__)
app.secret_key = 'pycharm_library_secret_key'
db_manager = DatabaseManager() 

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    role = request.form.get('role')
    password = request.form.get('password')
    
    if role == 'admin' and password == 'admin': 
        session['role'] = 'admin'
        flash('Admin login successful!', 'success')
        return redirect(url_for('admin_dashboard'))
    elif role == 'student':
        session['role'] = 'student'
        flash('Student access granted! Head to the Chatbot.', 'success')
        return redirect(url_for('student_dashboard'))
    else:
        flash('Invalid password for Admin role.', 'danger')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('role', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# --- ADMIN Interface Routes ---

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))
    
    books = db_manager.get_all_books()
    return render_template('admin_dashboard.html', books=books)

@app.route('/admin/add', methods=['POST'])
def admin_add_book():
    if session.get('role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))
        
    try:
        name = request.form['name']
        subject = request.form['subject']
        price = float(request.form['price'])
        edition = int(request.form['edition'])
        
        book_id = db_manager.add_book(name, subject, price, edition)
        
        if book_id:
            flash(f"✅ Book '{name}' added successfully! ID: {book_id}", 'success')
        else:
             flash("❌ Failed to add book to the database.", 'danger')
        
    except ValueError:
        flash("❌ Error: Price must be a number and Edition must be an integer.", 'danger')
    except Exception as e:
        flash(f"❌ Application Error: {e}", 'danger')
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/remove/<int:book_id>', methods=['POST'])
def admin_remove_book(book_id):
    if session.get('role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))
        
    if db_manager.remove_book(book_id):
        flash(f"✅ Book ID {book_id} removed successfully.", 'success')
    else:
        flash(f"⚠️ Book ID {book_id} not found.", 'warning')
        
    return redirect(url_for('admin_dashboard'))

# --- STUDENT Interface (The Conversational Chatbot) ---

@app.route('/student')
def student_dashboard():
    """Renders the main Chatbot interface."""
    if session.get('role') != 'student':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))
        
    return render_template('student_dashboard.html')

@app.route('/student/chat', methods=['POST'])
def student_chat():
    """Handles conversational search requests via AJAX and returns JSON."""
    if session.get('role') != 'student':
        return jsonify({'message': 'Session expired. Please log in again.', 'type': 'danger'}), 401
    
    data = request.get_json()
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'message': 'Please ask a question about a book or subject.', 'type': 'warning'})

    # 1. Search for a direct match
    found_books = find_books(db_manager, query)
    
    if found_books:
        # Format the results into an HTML list for the chatbot response
        response_html = f"✅ I found **{len(found_books)}** book(s) matching your request for '{query}':<br><ul>"
        for book in found_books:
            response_html += f"<li>**{book['name']}** ({book['subject']}) - Edition {book['edition']} (ID: {book['book_id']})</li>"
        response_html += "</ul>"
        
        return jsonify({'message': response_html, 'type': 'success'})
    else:
        # 2. If not found, provide recommendations
        recommendation_message, recommended_books = get_recommendations(db_manager, query, found_books)
        
        if recommended_books:
            response_html = f"{recommendation_message}<br><ul>"
            for book in recommended_books:
                response_html += f"<li>**{book['name']}** - Edition {book['edition']}</li>"
            response_html += "</ul>"
            return jsonify({'message': response_html, 'type': 'info'})
        else:
            return jsonify({'message': recommendation_message, 'type': 'warning'})

if __name__ == '__main__':
    app.run(debug=True)