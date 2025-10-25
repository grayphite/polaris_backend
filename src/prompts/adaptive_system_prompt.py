"""
Adaptive System Prompt
Intelligent system prompt that adapts to tax and general questions
"""

def get_adaptive_system_prompt(conversation_context: str = None, rag_metadata: dict = None, 
                              question_type: str = "auto") -> str:
    """
    Get an adaptive system prompt that handles both tax and general questions
    
    Args:
        conversation_context: Previous conversation context
        rag_metadata: RAG metadata containing sources and context chunks
        question_type: "tax", "general", or "auto" (auto-detect)
        
    Returns:
        Adaptive system prompt string
    """
    
    # Tax Agent RAG Configuration
    tax_agent_rag = {
        "stable_sources": {
            "us_federal": {
                "irc": "Internal Revenue Code - Title 26",
                "treasury_regs": "26 CFR - Current regulations",
                "irs_publications": "Static IRS guidance documents"
            },
            "brazil_federal": {
                "tax_code": "CTN and federal laws",
                "rfb_instructions": "Current Normative Instructions",
                "decrees": "Federal regulatory decrees"
            },
            "international": {
                "oecd": "Model Convention and TP Guidelines",
                "treaties": "FATCA and TIEA agreements"
            }
        },
        "proprietary_content": {
            "internal_memos": "Company tax positions",
            "client_structures": "Common scenarios",
            "practical_guides": "Implementation playbooks"
        }
    }
    
    # Base adaptive prompt
    base_prompt = (
        "You are an intelligent AI assistant with specialized expertise in tax matters, legal affairs, and general knowledge. "
        "You can handle tax-specific questions, legal questions, and general inquiries with appropriate expertise.\n\n"
        
        "CORE CAPABILITIES:\n"
        "=== TAX EXPERTISE ===\n"
        "When dealing with tax-related questions, you have access to comprehensive tax knowledge:\n\n"
        
        "US FEDERAL TAX:\n"
        "- IRC: Internal Revenue Code - Title 26\n"
        "- Treasury Regulations: 26 CFR - Current regulations\n"
        "- IRS Publications: Static IRS guidance documents\n\n"
        
        "BRAZIL FEDERAL TAX:\n"
        "- Tax Code: CTN and federal laws\n"
        "- RFB Instructions: Current Normative Instructions\n"
        "- Decrees: Federal regulatory decrees\n\n"
        
        "INTERNATIONAL TAX:\n"
        "- OECD: Model Convention and TP Guidelines\n"
        "- Treaties: FATCA and TIEA agreements\n\n"
        
        "=== LEGAL EXPERTISE ===\n"
        "When dealing with legal questions, you have access to comprehensive legal knowledge:\n\n"
        
        "US LEGAL SYSTEM:\n"
        "- Federal and state laws, regulations, and statutes\n"
        "- Case law and legal precedents\n"
        "- Constitutional law and civil rights\n"
        "- Business law, contract law, and corporate law\n"
        "- Intellectual property law (patents, copyrights, trademarks)\n"
        "- Employment law and labor regulations\n"
        "- Family law, property law, and real estate law\n\n"
        
        "BRAZIL LEGAL SYSTEM:\n"
        "- Código Civil Brasileiro (Brazilian Civil Code)\n"
        "- Código de Processo Civil (Civil Procedure Code)\n"
        "- Constituição Federal (Federal Constitution)\n"
        "- Leis complementares e ordinárias\n"
        "- Jurisprudência e precedentes judiciais\n\n"
        
        "INTERNATIONAL LEGAL:\n"
        "- International treaties and agreements\n"
        "- Cross-border legal frameworks\n"
        "- International business law\n"
        "- Human rights and international law\n\n"
        
        "=== GENERAL EXPERTISE ===\n"
        "For non-tax, non-legal questions, you can provide:\n"
        "- General knowledge and information\n"
        "- Business and professional guidance\n"
        "- Technical explanations\n"
        "- Problem-solving assistance\n"
        "- Educational content\n\n"
        
        "RESPONSE ADAPTATION:\n"
        "=== FOR TAX QUESTIONS ===\n"
        "- Use specialized tax terminology and references\n"
        "- Cite specific tax codes, sections, and regulations\n"
        "- Explain tax implications and compliance requirements\n"
        "- Reference jurisdiction-specific tax laws (US, Brazil, International)\n"
        "- Provide practical tax guidance while noting limitations\n\n"
        
        "=== FOR LEGAL QUESTIONS ===\n"
        "- Use precise legal terminology and references\n"
        "- Cite specific laws, statutes, regulations, and case law\n"
        "- Explain legal implications and compliance requirements\n"
        "- Reference jurisdiction-specific legal frameworks (US, Brazil, International)\n"
        "- Provide practical legal guidance while noting limitations\n"
        "- Distinguish between different areas of law (civil, criminal, constitutional, etc.)\n"
        "- Reference legal precedents and case law when applicable\n\n"
        
        "=== FOR GENERAL QUESTIONS ===\n"
        "- Use clear, accessible language\n"
        "- Provide comprehensive, well-structured answers\n"
        "- Offer practical insights and examples\n"
        "- Maintain professional but approachable tone\n"
        "- Focus on accuracy and helpfulness\n\n"
        
        "RESPONSE FORMAT:\n"
        "- Use plain text only (no markdown, bullet points, or special formatting)\n"
        "- Be concise yet comprehensive enough to address the query fully\n"
        "- Structure responses logically: key findings first, followed by supporting details\n"
        "- Use clear paragraph breaks for readability\n\n"
        
        "CRITICAL LIMITATIONS:\n"
        "- For tax questions: Always clarify that you do not provide specific tax advice\n"
        "- For general questions: Acknowledge when information may be time-sensitive or jurisdiction-dependent\n"
        "- State when professional consultation is recommended\n"
        "- Never guarantee specific outcomes or suggest strategies without proper context\n"
        "- Recommend consulting qualified professionals for specific situations\n\n"
        
        "TONE AND STYLE:\n"
        "- Professional and objective\n"
        "- Clear and accessible while maintaining accuracy\n"
        "- Respectful and neutral\n"
        "- Direct and practical, using appropriate terminology for the subject matter\n"
        "- Adapt your expertise level to match the question complexity"
    )
    
    # Add RAG enhancement if sources are provided
    if rag_metadata and rag_metadata.get('rag_enabled'):
        sources = rag_metadata.get('sources', [])
        context_chunks = rag_metadata.get('context_chunks', [])
        
        if sources or context_chunks:
            rag_enhancement = "\n\n=== RAG ENHANCED CONTEXT ===\n"
            rag_enhancement += "Relevant documents found:\n"
            
            # Add context chunks with detailed information
            for i, chunk in enumerate(context_chunks[:5], 1):  # Limit to 5 chunks
                source = chunk.get('source', 'Unknown')
                score = chunk.get('score', 0)
                text = chunk.get('text', '')[:500]  # Limit text length
                
                rag_enhancement += f"\n{i}. Source: {source} (Relevance: {score:.3f})\n"
                rag_enhancement += f"Content: {text}...\n"
            
            rag_enhancement += f"\nSources: {', '.join(sources)}\n"
            rag_enhancement += "\nIMPORTANT: When using information from the context above, ALWAYS mention the specific source. Include:\n"
            rag_enhancement += "- Document/source name\n"
            rag_enhancement += "- Relevant jurisdiction or authority when applicable\n"
            rag_enhancement += "- Specific section, article, or regulation if available\n"
            rag_enhancement += "- Be specific about the origin of each piece of information\n\n"
            
            rag_enhancement += "CRITICAL INSTRUCTIONS:\n"
            rag_enhancement += "- If you use information from the context above, ALWAYS mention the specific source\n"
            rag_enhancement += "- Indicate the jurisdiction or authority when applicable\n"
            rag_enhancement += "- Be transparent about where each piece of information comes from\n"
            rag_enhancement += "- Combine context information with your general knowledge when appropriate\n"
            rag_enhancement += "=== END RAG CONTEXT ===\n"
            
            base_prompt += rag_enhancement
    
    # Add conversation context if provided
    if conversation_context:
        context_section = f"\n\n=== CONVERSATION CONTEXT ===\n"
        context_section += f"Previous conversation:\n{conversation_context}\n"
        context_section += "=== END CONVERSATION CONTEXT ===\n"
        base_prompt += context_section
    
    return base_prompt


def detect_question_type(user_question: str) -> str:
    """
    Detect if a question is tax-related, legal, or general
    
    Args:
        user_question: The user's question
        
    Returns:
        "tax" for tax-related questions, "legal" for legal questions, "general" for others
    """
    
    # Tax-related keywords
    tax_keywords = [
        'tax', 'taxes', 'taxation', 'taxable', 'deduction', 'deductible',
        'irs', 'internal revenue', 'federal tax', 'state tax', 'income tax',
        'corporate tax', 'business tax', 'tax return', 'tax filing',
        'tax code', 'tax law', 'tax regulation', 'tax compliance',
        'ctn', 'código tributário', 'receita federal', 'rfb',
        'oecd', 'tax treaty', 'cross-border', 'transfer pricing',
        'tax planning', 'tax strategy', 'tax advice', 'tax professional'
    ]
    
    # Legal-related keywords
    legal_keywords = [
        'legal', 'law', 'laws', 'lawsuit', 'litigation', 'court', 'judge',
        'attorney', 'lawyer', 'legal advice', 'legal counsel', 'legal requirement',
        'contract', 'agreement', 'breach', 'liability', 'liabilities',
        'statute', 'regulation', 'compliance', 'legal process', 'legal procedure',
        'civil law', 'criminal law', 'constitutional', 'jurisdiction',
        'legal document', 'legal notice', 'legal action', 'legal rights',
        'intellectual property', 'patent', 'copyright', 'trademark',
        'employment law', 'labor law', 'divorce', 'family law',
        'property law', 'real estate law', 'business law', 'corporate law',
        'legal precedent', 'case law', 'legal opinion', 'legal framework'
    ]
    
    # Convert to lowercase for comparison
    question_lower = user_question.lower()
    
    # Check for tax keywords first (tax questions are more specific)
    for keyword in tax_keywords:
        if keyword in question_lower:
            return "tax"
    
    # Check for legal keywords
    for keyword in legal_keywords:
        if keyword in question_lower:
            return "legal"
    
    # Default to general for non-tax, non-legal questions
    return "general"


def get_tax_agent_rag_configuration():
    """
    Get the tax agent RAG configuration for reference
    
    Returns:
        Tax agent RAG configuration dictionary
    """
    return {
        "stable_sources": {
            "us_federal": {
                "irc": "Internal Revenue Code - Title 26",
                "treasury_regs": "26 CFR - Current regulations",
                "irs_publications": "Static IRS guidance documents"
            },
            "brazil_federal": {
                "tax_code": "CTN and federal laws",
                "rfb_instructions": "Current Normative Instructions",
                "decrees": "Federal regulatory decrees"
            },
            "international": {
                "oecd": "Model Convention and TP Guidelines",
                "treaties": "FATCA and TIEA agreements"
            }
        },
        "proprietary_content": {
            "internal_memos": "Company tax positions",
            "client_structures": "Common scenarios",
            "practical_guides": "Implementation playbooks"
        }
    }
