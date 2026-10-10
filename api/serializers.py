from rest_framework import serializers


class ActionSerializer(serializers.Serializer):
    actor_id = serializers.CharField(max_length=32)
    action = serializers.ChoiceField(choices=["POST", "WITHDRAW", "CLAIM", "UNCLAIM", "APPROVE", "REJECT"])
    shift_id = serializers.CharField(max_length=32, required=False)
    listing_id = serializers.CharField(max_length=64, required=False)
