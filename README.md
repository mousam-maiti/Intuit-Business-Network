Design a Quickbooks Business Network Graph
Introduction
In this system design problem, you are tasked with designing a system within 
Quickbooks that e9iciently maps out a business network graph. You will identify 
relationships between businesses, focusing primarily on vendor-client connections. 
This system aims to help users visualize which business is selling to who and 
understand the network of their business interactions.
Problem Scope
Design a system that enables QuickBooks users to e9iciently navigate through their 
network of business relationships. This includes allowing them to view their vendors 
and clients, search for a specific business client-vendor relationship, and map the 
relationship between businesses on the network.
Use Cases
Your system should support the following primary use cases:
1. Business views their network: A user can view a map of their business's 
network, highlighting vendors and clients.
2. Business searches for a specific relationship: A user can search for a specific 
business and understand their direct and indirect relationships.
3. Business can grow the network: A user can add a new business as a 
vendor/client of their business. The proposed new business may or may not 
already exist in the network, but with di9erent descriptors (free-text 
category/name for example).
4. Service maintains high availability: The system should be highly available and 
responsive.
Constraints and Assumptions
• Assume we're dealing with 1 million businesses.
• Each business can have up to 100 direct relationships (vendors or clients).
• The system should support 10 million relationship searches per month.
• Relationships are undirected and weighted by transaction volume.
• Tra9ic is not evenly distributed; some relationships are queried more frequently.