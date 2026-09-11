from typing import Tuple, Optional
from support.models import FAQItem


class FAQService:
    @staticmethod
    def search_matching_faq(query: str, organization_id: int) -> Tuple[Optional[FAQItem], float]:
        """
        Searches FAQ items in the active organization for a matching query.
        Returns: (FAQItem or None, confidence_score)
        """
        if not query:
            return None, 0.0

        query_lower = query.lower().strip()
        
        # Retrieve all active FAQs for this organization
        faqs = FAQItem.objects.filter(
            organization_id=organization_id,
            is_active=True
        ).select_related('category')

        # 1. Exact match on question (case insensitive)
        for faq in faqs:
            if faq.question.lower().strip() == query_lower:
                return faq, 1.0

        # 2. Keyword check and text overlap
        query_words = {w.strip(",.?!()\"'") for w in query_lower.split() if len(w) > 2}
        best_match = None
        best_score = 0.0

        for faq in faqs:
            match_count = 0
            keywords_list = faq.keywords
            if isinstance(keywords_list, list):
                for kw in keywords_list:
                    kw_clean = str(kw).lower().strip()
                    # Exact keyword found in query
                    if kw_clean in query_lower:
                        match_count += 2
                    # Word overlaps
                    for word in query_words:
                        if word == kw_clean or (len(word) > 4 and word in kw_clean) or (len(kw_clean) > 4 and kw_clean in word):
                            match_count += 1
            
            # Text overlap in question field
            q_lower = faq.question.lower()
            for word in query_words:
                if word in q_lower:
                    match_count += 1

            if match_count > 0:
                # Calculate simple confidence score
                score = min(0.95, 0.4 + (match_count * 0.1))
                if score > best_score:
                    best_score = score
                    best_match = faq

        # If best score is above confidence threshold, return it
        if best_match and best_score >= 0.7:
            return best_match, best_score

        return None, 0.0
