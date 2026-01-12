#!/usr/bin/env python3
"""
Google Maps Places API (New) Scraper for West Palm Beach, FL Business Listings

This script scrapes business listings from Google Maps Places API (New) using text search.
It extracts business information and saves both raw and filtered results.

Usage:
    python google_maps_scraper.py

Requirements:
    - Google Maps Places API key (set GOOGLE_MAPS_API_KEY environment variable)
    - requests library: pip install requests
"""

import os
import json
import time
import logging
from typing import List, Dict, Set, Optional
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('google_maps_scraper.log')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
if os.path.exists('.env'):
    with open('.env', 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value.strip().strip("'").strip('"')

# Configuration
API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', 'AIzaSyDmrFPvfjhVMYSLP_XQrhfSxqcUkiHafc0')
LOCATION = 'West Palm Beach, FL'
MAX_SEARCHES = 9000  # Leave buffer under 10,000 limit
OUTPUT_DIR = 'C:/Users/User/Downloads'
RAW_OUTPUT = os.path.join(OUTPUT_DIR, 'wpb_mega_list_raw.json')
FILTERED_OUTPUT = os.path.join(OUTPUT_DIR, 'wpb_mega_list_filtered.json')

# Search categories organized by type
SEARCH_CATEGORIES = {
    'Professional Services': [
        'lawyers', 'attorneys', 'law firms', 'personal injury lawyers',
        'family lawyers', 'criminal defense attorneys', 'immigration lawyers',
        'accountants', 'CPAs', 'bookkeepers', 'tax preparers',
        'financial advisors', 'wealth managers', 'investment advisors',
        'insurance agents', 'insurance brokers', 'life insurance', 'auto insurance',
        'real estate agents', 'realtors', 'real estate brokers', 'property managers',
        'mortgage brokers', 'loan officers'
    ],
    'Medical/Health': [
        'dentists', 'orthodontists', 'pediatric dentists', 'cosmetic dentists',
        'doctors', 'physicians', 'medical clinics', 'urgent care',
        'chiropractors', 'physical therapists', 'massage therapists',
        'veterinarians', 'animal hospitals', 'pet clinics',
        'mental health counselors', 'therapists', 'psychologists',
        'dermatologists', 'med spas', 'cosmetic surgery'
    ],
    'Home Services': [
        'general contractors', 'home builders', 'remodeling contractors',
        'plumbers', 'electricians', 'HVAC', 'air conditioning repair',
        'landscapers', 'lawn care', 'tree service', 'irrigation',
        'roofers', 'roofing contractors', 'gutter services',
        'pool service', 'pool cleaning', 'pool repair',
        'pest control', 'termite control', 'exterminator',
        'cleaning services', 'maid service', 'house cleaning',
        'painters', 'painting contractors', 'interior painting',
        'flooring', 'carpet installation', 'tile contractors',
        'garage door repair', 'handyman services'
    ],
    'Hospitality/Food': [
        'restaurants', 'Italian restaurants', 'Mexican restaurants',
        'Asian restaurants', 'steakhouses', 'seafood restaurants',
        'pizza', 'cafes', 'coffee shops',
        'catering', 'event catering', 'wedding catering',
        'bars', 'nightclubs', 'breweries', 'wine bars',
        'hotels', 'motels', 'bed and breakfast',
        'event venues', 'wedding venues', 'banquet halls'
    ],
    'Personal Services': [
        'salons', 'hair salons', 'beauty salons', 'nail salons', 'barbershops',
        'spas', 'day spas', 'massage spas',
        'pet grooming', 'dog grooming',
        'gyms', 'fitness centers', 'yoga studios', 'personal trainers',
        'photography', 'wedding photographers', 'portrait photographers',
        'dry cleaners', 'laundry services',
        'auto repair', 'auto body shops', 'car detailing', 'oil change'
    ],
    'Education/Training': [
        'tutoring', 'tutoring centers', 'math tutors',
        'daycare', 'childcare', 'preschool',
        'dance studios', 'martial arts', 'karate schools',
        'driving schools', 'music lessons',
        'language schools', 'training centers'
    ],
    'Retail/Specialty': [
        'auto parts', 'auto accessories',
        'furniture stores', 'home decor',
        'boutiques', 'clothing stores',
        'jewelry stores', 'jewelers',
        'florists', 'flower shops',
        'sporting goods stores',
        'pet stores', 'pet supplies'
    ]
}


class GoogleMapsScraper:
    """Google Maps Places API (New) scraper for business listings."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.search_count = 0
        self.raw_results = []
        self.errors = []

    def _make_request(self, url: str, body: Dict) -> Optional[Dict]:
        """Make API request with error handling."""
        try:
            import requests
            headers = {
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': self.api_key,
                'X-Goog-FieldMask': 'places.id,places.displayName,places.formattedAddress,places.internationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount,places.types'
            }
            response = requests.post(url, headers=headers, json=body, timeout=30)
            
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP Error: {e}")
                logger.error(f"Response body: {response.text}")
                self.errors.append(f"HTTP Error: {e} - Body: {response.text}")
                return None

            data = response.json()

            if 'places' in data:
                return data
            else:
                error_msg = f"API Error: {data.get('error', {}).get('message', 'Unknown error')}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                return None

        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return None

    def search_places(self, query: str) -> List[Dict]:
        """
        Search for places using Places API (New) text search.

        Args:
            query: Search query string

        Returns:
            List of place results
        """
        if self.search_count >= MAX_SEARCHES:
            logger.warning(f"Reached maximum search limit ({MAX_SEARCHES})")
            return []

        body = {
            'textQuery': f"{query} in {LOCATION}",
            'pageSize': 20
        }

        logger.info(f"Searching for: '{query}'")
        result = self._make_request("https://places.googleapis.com/v1/places:searchText", body)

        if result and 'places' in result:
            self.search_count += 1
            places = result['places']
            logger.info(f"  Found {len(places)} results (total searches: {self.search_count})")
            return places

        self.search_count += 1
        return []

    def extract_business_data(self, place: Dict) -> Dict:
        """Extract relevant business data from API response."""
        return {
            'name': place.get('displayName', {}).get('text', ''),
            'address': place.get('formattedAddress', ''),
            'phone': place.get('internationalPhoneNumber', ''),
            'website': place.get('websiteUri', ''),
            'rating': place.get('rating', 0),
            'review_count': place.get('userRatingCount', 0),
            'types': place.get('types', []),
            'place_id': place.get('id', ''),
            'scraped_at': datetime.now().isoformat()
        }

    def run_all_searches(self) -> List[Dict]:
        """Run all configured search categories."""
        logger.info(f"Starting Google Maps scraping for {LOCATION}")
        logger.info(f"Total categories to search: {sum(len(v) for v in SEARCH_CATEGORIES.values())}")
        logger.info(f"Maximum searches allowed: {MAX_SEARCHES}")

        all_places = []

        for category, queries in SEARCH_CATEGORIES.items():
            logger.info(f"\n{'='*60}")
            logger.info(f"Category: {category}")
            logger.info(f"{'='*60}")

            for query in queries:
                if self.search_count >= MAX_SEARCHES:
                    logger.warning(f"Reached maximum search limit ({MAX_SEARCHES})")
                    break

                places = self.search_places(query)
                if places:
                    for place in places:
                        business_data = self.extract_business_data(place)
                        business_data['search_category'] = category
                        business_data['search_query'] = query
                        all_places.append(business_data)

                # Small delay between queries to be respectful
                time.sleep(0.5)

            if self.search_count >= MAX_SEARCHES:
                break

        self.raw_results = all_places
        return all_places

    def save_raw_results(self, filepath: str) -> None:
        """Save raw results to JSON file."""
        output_data = {
            'metadata': {
                'location': LOCATION,
                'total_searches': self.search_count,
                'total_businesses': len(self.raw_results),
                'scraped_at': datetime.now().isoformat(),
                'max_searches_allowed': MAX_SEARCHES
            },
            'results': self.raw_results,
            'errors': self.errors
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Raw results saved to: {filepath}")

    def filter_and_save_results(self, output_path: str) -> Dict:
        """
        Filter results by removing duplicates and applying quality filters.

        Returns:
            Dictionary with filtering statistics
        """
        # Remove duplicates by name + address
        seen: Set[str] = set()
        unique_places = []

        for place in self.raw_results:
            key = f"{place['name'].lower()}|{place['address'].lower()}"
            if key not in seen:
                seen.add(key)
                unique_places.append(place)

        # Apply filters: has website, 10+ reviews, 3.5+ rating
        filtered_places = [
            place for place in unique_places
            if place['website'] and
            place['review_count'] >= 10 and
            place['rating'] >= 3.5
        ]

        stats = {
            'total_raw': len(self.raw_results),
            'duplicates_removed': len(self.raw_results) - len(unique_places),
            'unique': len(unique_places),
            'filtered': len(filtered_places),
            'filtered_out': len(unique_places) - len(filtered_places)
        }

        output_data = {
            'metadata': {
                'location': LOCATION,
                'total_searches': self.search_count,
                'scraped_at': datetime.now().isoformat(),
                'filtering_stats': stats
            },
            'results': filtered_places
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Filtered results saved to: {output_path}")
        logger.info(f"Filtering stats: {stats}")

        return stats


def main():
    """Main execution function."""
    # Check API key
    if API_KEY == 'YOUR_API_KEY_HERE' or not API_KEY:
        logger.error("Please set your Google Maps API key:")
        logger.error("  Windows: set GOOGLE_MAPS_API_KEY=your_key_here")
        logger.error("  PowerShell: $env:GOOGLE_MAPS_API_KEY='your_key_here'")
        logger.error("  Linux/Mac: export GOOGLE_MAPS_API_KEY='your_key_here'")
        return

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Create scraper instance
    scraper = GoogleMapsScraper(API_KEY)

    # Run all searches
    start_time = time.time()
    scraper.run_all_searches()
    elapsed_time = time.time() - start_time

    # Save raw results
    scraper.save_raw_results(RAW_OUTPUT)

    # Filter and save results
    stats = scraper.filter_and_save_results(FILTERED_OUTPUT)

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("SCRAPING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Location: {LOCATION}")
    logger.info(f"Total searches performed: {scraper.search_count}/{MAX_SEARCHES}")
    logger.info(f"Total businesses extracted (raw): {len(scraper.raw_results)}")
    logger.info(f"Unique businesses: {stats['unique']}")
    logger.info(f"Filtered businesses (quality leads): {stats['filtered']}")
    logger.info(f"Duplicates removed: {stats['duplicates_removed']}")
    logger.info(f"Filtered out (low quality): {stats['filtered_out']}")
    logger.info(f"Elapsed time: {elapsed_time:.2f} seconds")
    logger.info(f"\nOutput files:")
    logger.info(f"  Raw: {RAW_OUTPUT}")
    logger.info(f"  Filtered: {FILTERED_OUTPUT}")

    if scraper.errors:
        logger.warning(f"\nErrors encountered: {len(scraper.errors)}")


if __name__ == '__main__':
    main()
