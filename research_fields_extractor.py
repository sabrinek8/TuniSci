import json
import re
from typing import List, Dict, Set
import pandas as pd

class ResearchFieldExtractor:
    def __init__(self):
        pass
    
    def clean_interest(self, interest: str) -> str:
        if not interest:
            return ""
        
        # Remove extra whitespace and convert to title case
        cleaned = re.sub(r'\s+', ' ', interest.strip())
        
        # Remove punctuation at the end
        cleaned = re.sub(r'[.,;!?]+$', '', cleaned)
        
        # Capitalize first letter of each word for consistency
        cleaned = cleaned.title()
        
        return cleaned
    
    def extract_unique_interests(self, authors_data: List[Dict]) -> Set[str]:
        unique_interests = set()
        
        for author in authors_data:
            interests = author.get('profile_interests', [])
            if interests:
                for interest in interests:
                    cleaned_interest = self.clean_interest(interest)
                    if cleaned_interest:  
                        unique_interests.add(cleaned_interest)
        
        return unique_interests
    
    def calculate_field_statistics(self, authors_data: List[Dict], unique_interests: Set[str]) -> Dict:
        field_stats = {}
        
        for interest in unique_interests:
            h_indices = []
            i10_indices = []
            authors_in_field = []
            
            # Find all authors with this interest
            for author in authors_data:
                author_interests = author.get('profile_interests', [])
                if author_interests:
                    for author_interest in author_interests:
                        if self.clean_interest(author_interest) == interest:
                            h_index = int(author.get('hindex', 0))
                            i10_index = int(author.get('i10index', 0))
                            
                            h_indices.append(h_index)
                            i10_indices.append(i10_index)
                            authors_in_field.append({
                                'name': author.get('profile_name', 'N/A'),
                                'affiliation': author.get('profile_affiliations', 'N/A'),
                                'hindex': h_index,
                                'i10index': i10_index
                            })
                            break  
            
            if h_indices:  
                field_stats[interest] = {
                    'count': len(h_indices),
                    'average_h_index': round(sum(h_indices) / len(h_indices), 2),
                    'average_i10_index': round(sum(i10_indices) / len(i10_indices), 2),
                    'max_h_index': max(h_indices),
                    'min_h_index': min(h_indices),
                    'max_i10_index': max(i10_indices),
                    'min_i10_index': min(i10_indices),
                    'total_h_index': sum(h_indices),
                    'total_i10_index': sum(i10_indices),
                    'authors': sorted(authors_in_field, key=lambda x: x['hindex'], reverse=True)
                }
        
        return field_stats
    
    def process_authors_file(self, input_file: str, output_file: str = None) -> Dict:        
        print(f"Loading authors data from {input_file}...")
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                authors_data = json.load(f)
        except FileNotFoundError:
            print(f"❌ Error: Could not find input file '{input_file}'")
            return {}
        except json.JSONDecodeError:
            print(f"❌ Error: Invalid JSON in file '{input_file}'")
            return {}
        
        print(f"Processing {len(authors_data)} authors...")
        
        print("Extracting unique research interests...")
        unique_interests = self.extract_unique_interests(authors_data)
        print(f"Found {len(unique_interests)} unique research interests")
        
        print("Calculating statistics for each research field...")
        field_stats = self.calculate_field_statistics(authors_data, unique_interests)
        
        sorted_field_stats = dict(sorted(field_stats.items(), 
                                       key=lambda x: x[1]['average_h_index'], 
                                       reverse=True))
        
        # Prepare results
        results = {
            'research_fields_statistics': sorted_field_stats,
            'total_authors': len(authors_data),
            'total_unique_fields': len(field_stats),
            'summary': {
                'top_field_by_avg_h_index': max(field_stats.items(), key=lambda x: x[1]['average_h_index']) if field_stats else None,
                'most_popular_field': max(field_stats.items(), key=lambda x: x[1]['count']) if field_stats else None,
                'field_with_highest_max_h_index': max(field_stats.items(), key=lambda x: x[1]['max_h_index']) if field_stats else None
            }
        }
        
      
        if output_file:
            print(f"Saving research fields analysis to {output_file}...")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
        
        self.print_summary(results)
        
        return results
    
    def print_summary(self, results: Dict):
        """Print a summary of the field extraction results"""
        print("\n" + "="*70)
        print("RESEARCH FIELDS ANALYSIS SUMMARY")
        print("="*70)
        
        field_stats = results['research_fields_statistics']
        
        print(f"\nTotal Authors: {results['total_authors']}")
        print(f"Total Unique Research Fields: {results['total_unique_fields']}")
        
        if results['summary']['top_field_by_avg_h_index']:
            top_field, top_stats = results['summary']['top_field_by_avg_h_index']
            print(f"Top Field by Average H-Index: {top_field} (Avg: {top_stats['average_h_index']})")
        
        if results['summary']['most_popular_field']:
            popular_field, popular_stats = results['summary']['most_popular_field']
            print(f"Most Popular Field: {popular_field} ({popular_stats['count']} authors)")
        
        print(f"\nTop 15 Research Fields by Average H-Index:")
        print("-" * 70)
        print(f"{'Research Field':<35} {'Authors':<8} {'Avg H-Index':<12} {'Max H-Index'}")
        print("-" * 70)
        
        for i, (field, stats) in enumerate(list(field_stats.items())[:15], 1):
            field_display = field if len(field) <= 32 else field[:29] + "..."
            print(f"{field_display:<35} {stats['count']:<8} {stats['average_h_index']:<12} {stats['max_h_index']}")
        
        print(f"\nTop 10 Most Popular Research Fields:")
        print("-" * 50)
        sorted_by_count = sorted(field_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        
        for i, (field, stats) in enumerate(sorted_by_count[:10], 1):
            percentage = (stats['count'] / results['total_authors']) * 100
            field_display = field if len(field) <= 30 else field[:27] + "..."
            print(f"{i:2d}. {field_display:<32} {stats['count']:3d} authors ({percentage:.1f}%)")

def main():
    extractor = ResearchFieldExtractor()

    input_file = "authors_with_h_index.json"
    output_file = "research_fields_analysis.json"
    
    try:
        results = extractor.process_authors_file(input_file, output_file)
        
        if results:
            print(f"\n✅ Processing completed successfully!")
            print(f"📁 Research fields analysis saved to: {output_file}")
            
            # Create a simple CSV for easy viewing
            csv_file = "research_fields_summary.csv"
            field_stats = results['research_fields_statistics']
            
            # Convert to DataFrame for CSV export
            csv_data = []
            for field, stats in field_stats.items():
                csv_data.append({
                    'Research Field': field,
                    'Number of Authors': stats['count'],
                    'Average H-Index': stats['average_h_index'],
                    'Average i10-Index': stats['average_i10_index'],
                    'Max H-Index': stats['max_h_index'],
                    'Min H-Index': stats['min_h_index'],
                    'Total H-Index': stats['total_h_index']
                })
            
            df = pd.DataFrame(csv_data)
            df.to_csv(csv_file, index=False)
            print(f"📊 Summary CSV saved to: {csv_file}")
        
    except Exception as e:
        print(f"❌ Error processing data: {str(e)}")

if __name__ == "__main__":
    main()