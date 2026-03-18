"""GraphQL mutation strings for the Twingate Admin API."""

RESOURCE_ACCESS_ADD = """
mutation ResourceAccessAdd($resourceId: ID!, $access: [AccessInput!]!) {
  resourceAccessAdd(resourceId: $resourceId, access: $access) {
    ok
    error
    entity {
      id
      name
    }
  }
}
"""

RESOURCE_ACCESS_REMOVE = """
mutation ResourceAccessRemove($resourceId: ID!, $principalIds: [ID!]!) {
  resourceAccessRemove(resourceId: $resourceId, principalIds: $principalIds) {
    ok
    error
    entity {
      id
      name
    }
  }
}
"""
