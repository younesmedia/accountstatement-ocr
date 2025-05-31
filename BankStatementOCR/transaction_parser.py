import re
import logging
from datetime import datetime
from typing import List, Dict, Optional

class TransactionParser:
    """
    Parser for banking transaction lines extracted via OCR
    
    Handles French bank statement formats with date, description, amounts, and balance
    """
    
    def __init__(self):
        # French month abbreviations mapping
        self.french_months = {
            'janv': 1, 'jan': 1,
            'févr': 2, 'fév': 2, 'feb': 2,
            'mars': 3, 'mar': 3,
            'avr': 4, 'avril': 4,
            'mai': 5,
            'juin': 6, 'jun': 6,
            'juil': 7, 'juillet': 7,
            'août': 8, 'aou': 8, 'aout': 8,
            'sept': 9, 'sep': 9,
            'oct': 10, 'octobre': 10,
            'nov': 11, 'novembre': 11,
            'déc': 12, 'dec': 12, 'décembre': 12
        }
        
        # Patterns for transaction parsing
        self.date_pattern = r'(\d{1,2})\s*([a-zA-Zàâäéèêëïîôöùûüÿ]+)\.?\s*(\d{4})?'
        self.amount_pattern = r'€\s*([+-]?\d{1,3}(?:[,.\s]\d{3})*[,.]?\d{0,2})'
        self.transaction_pattern = r'(\d{1,2}\s*[a-zA-Zàâäéèêëïîôöùûüÿ]+\.?\s*\d{0,4})\s+(.+?)(?=€)'
        
    def parse_date(self, date_str: str, year: int = None) -> Optional[str]:
        """
        Parse French date format to ISO format (YYYY-MM-DD)
        
        Args:
            date_str: Date string like "4 avr. 2025" or "15 janv"
            year: Default year if not specified in date
            
        Returns:
            ISO formatted date string or None if parsing fails
        """
        try:
            match = re.search(self.date_pattern, date_str.lower())
            if not match:
                return None
            
            day = int(match.group(1))
            month_str = match.group(2).lower().rstrip('.')
            year_str = match.group(3)
            
            # Get month number from French abbreviation
            month = self.french_months.get(month_str)
            if not month:
                return None
            
            # Use provided year or current year as fallback
            if year_str:
                year = int(year_str)
            elif year is None:
                year = datetime.now().year
            
            # Create date and return ISO format
            date_obj = datetime(year, month, day)
            return date_obj.strftime('%Y-%m-%d')
            
        except (ValueError, AttributeError) as e:
            logging.debug(f"Date parsing error for '{date_str}': {e}")
            return None
    
    def parse_amount(self, amount_str: str) -> float:
        """
        Parse French currency amount to float
        
        Args:
            amount_str: Amount string like "€12,90" or "€1.234,56"
            
        Returns:
            Float value of the amount
        """
        try:
            # Remove currency symbol and whitespace
            amount_str = amount_str.replace('€', '').strip()
            
            # Handle French number format (comma as decimal separator)
            # If there's both comma and dot, assume comma is decimal
            if ',' in amount_str and '.' in amount_str:
                # Format like "1.234,56" - dot is thousands separator
                amount_str = amount_str.replace('.', '').replace(',', '.')
            elif ',' in amount_str:
                # Format like "12,90" - comma is decimal separator
                amount_str = amount_str.replace(',', '.')
            # If only dots, assume they're decimal separators for amounts < 1000
            
            # Remove any remaining spaces used as thousands separators
            amount_str = amount_str.replace(' ', '')
            
            return float(amount_str)
            
        except (ValueError, AttributeError) as e:
            logging.debug(f"Amount parsing error for '{amount_str}': {e}")
            return 0.0
    
    def extract_amounts(self, line: str) -> tuple:
        """
        Extract amount_out, amount_in, and balance from transaction line
        
        Args:
            line: Transaction line text
            
        Returns:
            Tuple of (amount_out, amount_in, balance) as floats
        """
        amounts = re.findall(self.amount_pattern, line)
        
        amount_out = None
        amount_in = None
        balance = None
        
        # Parse found amounts
        parsed_amounts = []
        for amount_str in amounts:
            amount = self.parse_amount(amount_str)
            parsed_amounts.append(amount)
        
        # Logic to determine which amount is which
        # Typically: [transaction_amount, balance] or [amount_out, amount_in, balance]
        if len(parsed_amounts) >= 2:
            # Last amount is usually the balance
            balance = parsed_amounts[-1]
            
            # If we have 2 amounts, first is transaction amount
            if len(parsed_amounts) == 2:
                transaction_amount = parsed_amounts[0]
                # Determine if it's outgoing or incoming based on context
                # Negative amounts or amounts that reduce balance are typically outgoing
                if transaction_amount < 0:
                    amount_out = abs(transaction_amount)
                else:
                    # Need to check if balance decreased
                    amount_out = transaction_amount
            
            # If we have 3 or more amounts, try to identify out/in/balance pattern
            elif len(parsed_amounts) >= 3:
                amount_out = parsed_amounts[0] if parsed_amounts[0] > 0 else None
                amount_in = parsed_amounts[1] if len(parsed_amounts) > 2 else None
                balance = parsed_amounts[-1]
        
        return amount_out, amount_in, balance
    
    def is_transaction_line(self, line: str) -> bool:
        """
        Check if a line appears to be a transaction line
        
        Args:
            line: Text line to check
            
        Returns:
            True if line looks like a transaction
        """
        # Must contain a date pattern and at least one amount
        has_date = bool(re.search(self.date_pattern, line.lower()))
        has_amount = bool(re.search(self.amount_pattern, line))
        
        # Should have reasonable length (not too short, not too long)
        reasonable_length = 20 <= len(line) <= 200
        
        return has_date and has_amount and reasonable_length
    
    def parse_transaction_line(self, line: str, default_year: int = None) -> Optional[Dict]:
        """
        Parse a single transaction line
        
        Args:
            line: Transaction line text
            default_year: Year to use if not specified in date
            
        Returns:
            Dictionary with transaction data or None if parsing fails
        """
        if not self.is_transaction_line(line):
            return None
        
        try:
            # Extract date
            date_match = re.search(self.date_pattern, line.lower())
            if not date_match:
                return None
            
            date_str = date_match.group(0)
            parsed_date = self.parse_date(date_str, default_year)
            if not parsed_date:
                return None
            
            # Extract description (text between date and first amount)
            # Find the end of the date
            date_end = date_match.end()
            amount_match = re.search(self.amount_pattern, line[date_end:])
            if not amount_match:
                return None
            
            # Description is between date and first amount
            description_start = date_end
            description_end = date_end + amount_match.start()
            description = line[description_start:description_end].strip()
            
            # Clean up description
            description = re.sub(r'\s+', ' ', description)
            
            # Extract amounts
            amount_out, amount_in, balance = self.extract_amounts(line[date_end:])
            
            transaction = {
                'date': parsed_date,
                'description': description,
                'amount_out': amount_out,
                'amount_in': amount_in,
                'balance': balance
            }
            
            logging.debug(f"Parsed transaction: {transaction}")
            return transaction
            
        except Exception as e:
            logging.debug(f"Error parsing transaction line '{line}': {e}")
            return None
    
    def parse_transactions(self, text_lines: List[str]) -> List[Dict]:
        """
        Parse all transactions from list of text lines
        
        Args:
            text_lines: List of text lines from OCR
            
        Returns:
            List of transaction dictionaries
        """
        transactions = []
        current_year = datetime.now().year
        
        # Try to find year from document
        for line in text_lines[:10]:  # Check first few lines for year
            year_match = re.search(r'\b(20\d{2})\b', line)
            if year_match:
                current_year = int(year_match.group(1))
                break
        
        logging.debug(f"Using year: {current_year}")
        
        # Process each line
        for line in text_lines:
            transaction = self.parse_transaction_line(line, current_year)
            if transaction:
                transactions.append(transaction)
        
        # Sort transactions by date
        transactions.sort(key=lambda x: x['date'])
        
        logging.info(f"Successfully parsed {len(transactions)} transactions")
        return transactions
