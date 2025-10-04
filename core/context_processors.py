from .models import Company

def company_context(request):
    """
    Context processor to add company details to all templates.
    Returns the first active company or None if no active company exists.
    """
    try:
        company = Company.objects.filter(is_active=True).first()
        return {'company': company}
    except Company.DoesNotExist:
        return {'company': None}