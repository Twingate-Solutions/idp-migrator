"""GraphQL query strings for the Twingate Admin API."""

# Page size used for nested access edge queries in LIST_RESOURCES
_ACCESS_PAGE_SIZE = 100

LIST_GROUPS = """
query ListGroups($first: Int, $after: String, $filter: GroupFilterInput) {
  groups(first: $first, after: $after, filter: $filter) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        name
        type
        originId
        isActive
        securityPolicy {
          id
          name
        }
      }
    }
    totalCount
  }
}
"""

LIST_RESOURCES = f"""
query ListResources($first: Int, $after: String) {{
  resources(first: $first, after: $after) {{
    pageInfo {{
      hasNextPage
      endCursor
    }}
    edges {{
      node {{
        id
        name
        address {{
          value
        }}
        isActive
        access(first: {_ACCESS_PAGE_SIZE}) {{
          edges {{
            node {{
              ... on Node {{
                id
              }}
            }}
            securityPolicy {{
              id
              name
            }}
            expiresAt
            accessPolicy {{
              mode
              durationSeconds
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
      }}
    }}
    totalCount
  }}
}}
"""

GET_RESOURCE_ACCESS = """
query GetResourceAccess($id: ID!, $first: Int, $after: String) {
  resource(id: $id) {
    access(first: $first, after: $after) {
      edges {
        node {
          ... on Node {
            id
          }
        }
        securityPolicy {
          id
          name
        }
        expiresAt
        accessPolicy {
          mode
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""
