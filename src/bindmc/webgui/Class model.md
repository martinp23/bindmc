Class model

- UIState
    - This class contains the current state of the user interface, so includes:
       - list of Models and index of active Model
       - List of simulations and field values from latest/active simulation
       - Graph state
       - component details

- Simulation
    - A simulation comprises: 
        - A Model
        - A set of parameters
        - Input data (i.e. components)
        - Output data (i.e. species concentrations)
        - A name or timestamp or other unique(?) slug
        - An optional comment

- Model
    - Comprises
        - A name (unique among all models in the UIState)
        - An optional comment
        - The string entered into the eqStr input box
        - The parsed equation matrix as a list of lists (np.array)
        - (A function that returns a list of BindingConstant parameters?)
        - A list of species
        - A list of components