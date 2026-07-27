from ragas.testset.persona import Persona
from ragas.testset.synthesizers import (
    SingleHopSpecificQuerySynthesizer,
    MultiHopSpecificQuerySynthesizer,
    MultiHopAbstractQuerySynthesizer
)

# Define Personas
PERSONAS = {
    "die_hard": Persona(
        name="The Die-Hard Fan", 
        role_description="An obsessed Giants fan who uses heavy jargon and asks emotional questions about team loyalty and player greatness."
    ),
    "casual_fan": Persona(
        name="The Casual Viewer", 
        role_description="A general fan asking simple, non-technical questions about schedules and basic roster info."
    ),
    "rival_hater": Persona(
        name="The Rival Hater", 
        role_description="A fan of a division rival (e.g., Eagles or Cowboys) who asks skeptical, biased, or leading questions designed to highlight the Giants' failures or weaknesses."
    )
}

# Define Distribution Logic (as a function to allow LLM injection)
def get_distribution(mode, llm):
    """
    Returns the distribution tuple required by Ragas.
    'mode' corresponds to the island type: 'deep', 'breadth', or 'bridge'
    """
    
    if mode == "deep":
        return [
            (SingleHopSpecificQuerySynthesizer(llm=llm), 0.1),
            (MultiHopSpecificQuerySynthesizer(llm=llm), 0.8),
            (MultiHopAbstractQuerySynthesizer(llm=llm), 0.1)
        ]
    
    elif mode == "breadth":
        return [
            (SingleHopSpecificQuerySynthesizer(llm=llm), 0.7),
            (MultiHopSpecificQuerySynthesizer(llm=llm), 0.2),
            (MultiHopAbstractQuerySynthesizer(llm=llm), 0.1)
        ]
    
    elif mode == "bridge":
        return [
            (SingleHopSpecificQuerySynthesizer(llm=llm), 0.1),
            (MultiHopSpecificQuerySynthesizer(llm=llm), 0.2),
            (MultiHopAbstractQuerySynthesizer(llm=llm), 0.7)
        ]
    
    # Default fallback
    return [
        (SingleHopSpecificQuerySynthesizer(llm=llm), 0.33),
        (MultiHopSpecificQuerySynthesizer(llm=llm), 0.33),
        (MultiHopAbstractQuerySynthesizer(llm=llm), 0.34)
    ]
