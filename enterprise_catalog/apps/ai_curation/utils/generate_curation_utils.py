"""
Utility functions for curation generation.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .algolia_utils import fetch_catalog_metadata_from_algolia
from .open_ai_utils import (
    get_filtered_subjects,
    get_keywords_to_prose,
    get_query_keywords,
)


def count_terms_in_description(search_terms, product_description):
    """
    Count the number of search terms found in the product description.

    Arguments:
        search_terms (list): A list of search terms
        product_description (str): The product description

    Returns:
        int: The number of search terms found in the product description
    """
    # Lowercase the search terms and product description for case-insensitive comparison
    search_terms_lower = [term.lower() for term in search_terms]
    product_description_lower = product_description.lower()

    count = 0

    # For each term in the lower-cased search terms.
    for term in search_terms_lower:
        # If the term is in the lower-cased product description,
        if term in product_description_lower:
            count += 1

    # Return count -- 0 if nothing found
    return count


def apply_subjects_filter(courses: list, subjects: set):
    """
    Filter the courses based on the given subjects.

    Arguments:
        courses (list): List of courses
        subjects (set): List of subjects to filter by

    Returns:
        list: List of courses filtered by the given subjects

    """
    return [course for course in courses if len(subjects.intersection(course['subjects'])) > 0]


def apply_keywords_filter(courses: list, keywords: list, kw_threshold: int = 2):
    """
    Filter the courses based on the given keywords.

    Arguments:
        courses (list): List of courses
        keywords (list): List of keywords to filter by
        kw_threshold (int): The minimum number of keywords that should be found in the course description

    Returns:
        list: List of courses filtered by the given keywords
    """
    return [
        course for course in courses if count_terms_in_description(
            keywords, f'Title: {course["title"]}, Skills taught: {", ".join(course["skills"])}'
        ) > kw_threshold
    ]


def get_cosine_similarities(search_string, product_strings):
    """
    Calculate the cosine similarity between the search string and product strings.

    Arguments:
        search_string (str): Search string
        product_strings (list): List of product strings

    Returns:
        list: List of cosine similarities between the search string and product strings.
    """
    # Combine search string and product strings
    all_strings = [search_string] + product_strings

    # Fit and transform the vectorizer on all strings
    tfidf_matrix = TfidfVectorizer().fit_transform(all_strings)

    # Calculate cosine similarity between search string and product strings
    return cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]


def apply_tfidf_filter(query: str, courses: list, tfidf_threshold: float):
    """
    Filter the courses based on the TF-IDF score.

    Arguments:
        query (str): Search query given by the user
        courses (list): List of courses
        tfidf_threshold (float): The minimum TF-IDF score that a course should have

    Returns:
        list: List of courses filtered by the TF-IDF score
    """
    keywords_to_prose = get_keywords_to_prose(query)

    for course in courses:
        # Get the cosine similarity between the keywords and the course
        course['tf_idf_score'] = get_cosine_similarities(keywords_to_prose, [
            (
                f'Title: {course["title"]}, Skills taught: {", ".join(course["skills"])}, Description: '
                f'{course["short_description"]}, Syllabus: {course["outcome"]}'
            )
        ])[0]

    return [course for course in courses if course['tf_idf_score'] > tfidf_threshold]


def apply_programs_filter(courses: list, programs: list):
    """
    Filter the programs based on the given subjects.

    Arguments:
        courses (list): List of Courses
        programs (list): List of Programs

    Returns:
        list: List of programs filtered by the given subjects

    """
    unique_programs = {', '.join(course['program_titles']) for course in courses}
    return [program for program in programs if program['title'] in unique_programs]


def generate_curation(query: str, catalog_name: str):
    """
    Generate the AI curation for the given query.

    Args:
        query (str): Search query given by the user
        catalog_name (str): Name of the catalog query to search

    Returns:
        dict: AI curation response
    """
    ocm_courses, exec_ed_courses, programs, subjects = fetch_catalog_metadata_from_algolia(catalog_name)
    filtered_subjects = set(get_filtered_subjects(query, subjects))
    # filter courses and exec ed courses based on the filtered subjects
    filtered_ocm_courses = apply_subjects_filter(ocm_courses, filtered_subjects)
    filtered_exec_ed_courses = apply_subjects_filter(exec_ed_courses, filtered_subjects)

    keywords = get_query_keywords(query)
    kw_threshold = 2
    # filter courses and exec ed courses based on the keywords
    filtered_ocm_courses = apply_keywords_filter(filtered_ocm_courses, keywords, kw_threshold)
    filtered_exec_ed_courses = apply_keywords_filter(filtered_exec_ed_courses, keywords, kw_threshold)

    tfidf_threshold = .2
    # filter courses and exec ed courses based on the TI-IDF score
    filtered_ocm_courses = apply_tfidf_filter(query, filtered_ocm_courses, tfidf_threshold)
    filtered_exec_ed_courses = apply_tfidf_filter(query, filtered_exec_ed_courses, tfidf_threshold)

    # filter programs based on the filtered courses
    filtered_programs = apply_programs_filter(filtered_ocm_courses + filtered_exec_ed_courses, programs)

    return {
        'query': query,
        'ocm_courses': filtered_ocm_courses,
        'exec_ed_courses': filtered_exec_ed_courses,
        'programs': filtered_programs,
    }
