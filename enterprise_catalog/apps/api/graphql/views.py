import graphene

class Query(graphene.ObjectType):
    hello = graphene.String(default='Hi there')

schema = graphene.Schema(query=Query)
