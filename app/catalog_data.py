"""IB Diploma subject catalogue.

Everything the app knows about a subject lives here: how to recognise its files on the
library drive, how it is assessed, and its syllabus units/topics.

Assessment outlines are the published structure at the time of writing; the UI always
points students to the official subject guide (also indexed from the drive) to confirm.

Topic strings use a compact form:  "code|name|search keywords|FLAGS"
  FLAGS: HL  = higher level only
         OPT = optional/choice topic, off until the student ticks it
         ON  = optional/choice topic that is pre-ticked (most commonly taught)
"""
from __future__ import annotations


def U(code: str, name: str, *topics: str, hours: tuple[int, int] | None = None) -> dict:
    out = []
    for t in topics:
        parts = (t.split("|") + ["", "", ""])[:4]
        flags = set(parts[3].upper().split()) if parts[3] else set()
        out.append({
            "code": parts[0].strip(), "name": parts[1].strip(),
            "kw": [k.strip() for k in parts[2].split(";") if k.strip()],
            "hl_only": "HL" in flags,
            "optional": bool(flags & {"OPT", "ON"}),
            "default_on": "OPT" not in flags,
        })
    return {"code": code, "name": name, "topics": out, "hours": hours}


def P(name: str, minutes: int, weight: float, detail: str = "") -> dict:
    return {"name": name, "minutes": minutes, "weight": weight, "detail": detail, "kind": "exam"}


def IA(name: str, weight: float, detail: str = "") -> dict:
    return {"name": name, "minutes": 0, "weight": weight, "detail": detail, "kind": "coursework"}


SCI_IA = "Scientific investigation, max 3,000 words. Criteria: research design, data analysis, conclusion, evaluation."

SUBJECTS: list[dict] = [
    # ───────────────────────────── Group 5 ─────────────────────────────
    dict(
        key="math_aa", name="Mathematics: Analysis and Approaches", short="Maths AA", group=5, levels=["HL", "SL"],
        syllabus_from=2021, family="math",
        papers=["mathematics analysis and approaches", "mathematics aa", "math aa", "maths aa", "math aahl", "math aasl"],
        papers_legacy=[("mathematics", "Old syllabus (Maths HL/SL, last exams 2020)"), ("further mathematics", "Old Further Maths HL")],
        books=["group 5 - mathematics/aa and ai", "group 5 - mathematics/mathematics higher level",
               "group 5 - mathematics/mathematics standard level", "group 5 - mathematics/background knowledge",
               "group 5 - mathematics/ib calculator guides", "group 5 - mathematics/further mathematics"],
        book_include=r"analysis and approaches|an[aá]lisis y enfoques|\baa\b|core topics|common core|course preparation|calculator|higher level|standard level|background|further",
        book_exclude=r"applications and interpretation|aplicaciones|\bai\b|\bmai\b",
        qb=["dp-mathematics-analysis-and-approaches", "dp-mathematics-hl", "dp-mathematics-sl", "dp-further-mathematics"],
        qb_paper=["math aa", "mathematics hl", "mathematics sl", "further mathematics"],
        sme=["maths aa"], sites=["ThinkIB/mathanalysis", "StudyIB/mathsanalysis", "ThinkIB/InThinking Math mocks"],
        names=["mathematics analysis and approaches", "mathematics hl and further mathematics hl", "mathematics sl", "mathematics hl", "further mathematics", "math aa"],
        assessment={
            "SL": [P("Paper 1", 90, 40, "No calculator · 80 marks · short + extended response"),
                   P("Paper 2", 90, 40, "Calculator (GDC) · 80 marks"),
                   IA("Mathematical exploration (IA)", 20, "12–20 pages. Criteria: presentation, communication, personal engagement, reflection, use of mathematics.")],
            "HL": [P("Paper 1", 120, 30, "No calculator · 110 marks"),
                   P("Paper 2", 120, 30, "Calculator (GDC) · 110 marks"),
                   P("Paper 3", 60, 20, "Calculator · 55 marks · two extended problem-solving questions"),
                   IA("Mathematical exploration (IA)", 20, "12–20 pages. Criteria: presentation, communication, personal engagement, reflection, use of mathematics.")],
        },
        units=[
            U("1", "Number and algebra",
              "1.1|Sequences and series|arithmetic sequence;geometric sequence;sigma notation;compound interest",
              "1.2|Exponents and logarithms|laws of logarithms;exponent;change of base",
              "1.3|Binomial theorem|binomial expansion;pascal's triangle",
              "1.4|Proof|deductive proof;proof by induction;contradiction;counterexample",
              "1.5|Complex numbers|complex number;argand;de moivre;polar form|HL",
              "1.6|Counting, partial fractions and systems of equations|permutations;combinations;partial fractions;system of linear equations|HL",
              hours=(19, 39)),
            U("2", "Functions",
              "2.1|Function basics, lines, inverse and composite|domain and range;inverse function;composite function;equation of a line",
              "2.2|Quadratic functions|quadratic;discriminant;completing the square;vertex",
              "2.3|Rational, exponential and logarithmic functions|rational function;asymptote;exponential function;logarithmic function",
              "2.4|Transformations of graphs|translation;stretch;reflection;transformations of graphs",
              "2.5|Polynomials|factor theorem;remainder theorem;sum and product of roots|HL",
              "2.6|Further functions and inequalities|modulus function;odd and even functions;inequalities;self-inverse|HL",
              hours=(21, 32)),
            U("3", "Geometry and trigonometry",
              "3.1|3D geometry and triangle trigonometry|sine rule;cosine rule;volume;surface area;bearing",
              "3.2|Radians, arcs and sectors|radian;arc length;sector area",
              "3.3|Trigonometric identities and equations|unit circle;pythagorean identity;double angle;trigonometric equation",
              "3.4|Trigonometric functions and graphs|sine curve;amplitude;period;trigonometric graph",
              "3.5|Reciprocal, inverse and compound-angle trigonometry|secant;cosecant;arcsin;compound angle|HL",
              "3.6|Vectors|scalar product;vector product;equation of a line;equation of a plane;vectors|HL",
              hours=(25, 51)),
            U("4", "Statistics and probability",
              "4.1|Descriptive statistics|mean;median;standard deviation;box plot;cumulative frequency",
              "4.2|Correlation and regression|pearson;regression line;correlation coefficient",
              "4.3|Probability|venn diagram;tree diagram;conditional probability;independent events",
              "4.4|Discrete random variables and the binomial distribution|expected value;binomial distribution;random variable",
              "4.5|Normal distribution|normal distribution;z-score;standardisation",
              "4.6|Bayes' theorem and continuous random variables|bayes;probability density function;continuous random variable|HL",
              hours=(27, 33)),
            U("5", "Calculus",
              "5.1|Limits and differentiation basics|derivative;gradient;limit;first principles",
              "5.2|Differentiation rules|chain rule;product rule;quotient rule;second derivative",
              "5.3|Applications of differentiation|optimisation;tangent;normal;stationary point;kinematics",
              "5.4|Integration and areas|definite integral;area under curve;antiderivative",
              "5.5|Further integration and volumes|integration by substitution;integration by parts;volume of revolution|HL",
              "5.6|Differential equations|separable;integrating factor;euler's method;differential equation|HL",
              "5.7|Maclaurin series and L'Hôpital's rule|maclaurin;l'hopital;implicit differentiation;related rates|HL",
              hours=(28, 55)),
        ],
    ),
    dict(
        key="math_ai", name="Mathematics: Applications and Interpretation", short="Maths AI", group=5, levels=["HL", "SL"],
        syllabus_from=2021, family="math",
        papers=["mathematics applications and interpretation", "mathematics ai", "math ai", "maths ai", "math aihl", "math aisl"],
        papers_legacy=[("mathematical studies", "Old syllabus (Mathematical Studies SL, last exams 2020)")],
        books=["group 5 - mathematics/aa and ai", "group 5 - mathematics/mathematical studies",
               "group 5 - mathematics/background knowledge", "group 5 - mathematics/ib calculator guides"],
        book_include=r"applications and interpretation|aplicaciones e interpretaci|\bai\b|\bmai\b|core topics|common core|course preparation|calculator|studies|background",
        book_exclude=r"analysis and approaches|an[aá]lisis y enfoques|\baa\b",
        qb=["dp-mathematics-applications-and-interpretation", "dp-mathematical-studies"],
        qb_paper=["math ai", "mathematical studies"],
        sme=["maths ai"], sites=["StudyIB/mathsapplications"],
        names=["mathematics applications and interpretation", "mathematical studies", "math ai"],
        assessment={
            "SL": [P("Paper 1", 90, 40, "Calculator · 80 marks · short response"),
                   P("Paper 2", 90, 40, "Calculator · 80 marks · extended response"),
                   IA("Mathematical exploration (IA)", 20, "12–20 pages. Same five criteria as Maths AA.")],
            "HL": [P("Paper 1", 120, 30, "Calculator · 110 marks"),
                   P("Paper 2", 120, 30, "Calculator · 110 marks"),
                   P("Paper 3", 60, 20, "Calculator · 55 marks · two extended problem-solving questions"),
                   IA("Mathematical exploration (IA)", 20, "12–20 pages.")],
        },
        units=[
            U("1", "Number and algebra",
              "1.1|Approximation, standard form and error|standard form;percentage error;significant figures",
              "1.2|Sequences and financial mathematics|arithmetic sequence;geometric sequence;compound interest;annuity;amortization",
              "1.3|Exponents and logarithms|logarithm;exponent",
              "1.4|Complex numbers|complex number;argand;polar form|HL",
              "1.5|Matrices|matrix;determinant;eigenvalue;eigenvector|HL",
              hours=(16, 29)),
            U("2", "Functions",
              "2.1|Linear models and function basics|linear function;domain and range;gradient",
              "2.2|Quadratic, exponential, cubic and sinusoidal models|quadratic model;exponential model;sinusoidal model;cubic",
              "2.3|Modelling skills|modelling;direct variation;inverse variation",
              "2.4|Further models and log scaling|logistic model;piecewise;log-log;semi-log|HL",
              "2.5|Composite, inverse functions and transformations|composite function;inverse function;transformation|HL",
              hours=(31, 42)),
            U("3", "Geometry and trigonometry",
              "3.1|3D geometry and triangle trigonometry|sine rule;cosine rule;volume;surface area",
              "3.2|Circles, arcs and sectors|arc length;sector area",
              "3.3|Voronoi diagrams|voronoi;perpendicular bisector;nearest neighbour",
              "3.4|Vectors and kinematics|vector;scalar product;vector product;kinematics|HL",
              "3.5|Graph theory|graph theory;adjacency matrix;kruskal;prim;chinese postman;travelling salesman|HL",
              "3.6|Matrix transformations|transformation matrix;rotation;enlargement|HL",
              hours=(18, 46)),
            U("4", "Statistics and probability",
              "4.1|Descriptive statistics|mean;median;standard deviation;box plot;histogram",
              "4.2|Correlation and regression|pearson;spearman;regression line",
              "4.3|Probability|venn diagram;tree diagram;conditional probability;expected value",
              "4.4|Binomial and normal distributions|binomial distribution;normal distribution",
              "4.5|Hypothesis testing|chi-squared;t-test;null hypothesis;p-value;goodness of fit",
              "4.6|Poisson, confidence intervals and further tests|poisson;confidence interval;type i error;central limit theorem|HL",
              "4.7|Transition matrices and Markov chains|markov chain;transition matrix;steady state|HL",
              hours=(36, 52)),
            U("5", "Calculus",
              "5.1|Differentiation and optimisation|derivative;gradient;optimisation;tangent",
              "5.2|Integration and the trapezoidal rule|definite integral;trapezoidal rule;area under curve",
              "5.3|Further calculus and related rates|chain rule;product rule;related rates;volume of revolution|HL",
              "5.4|Differential equations|euler's method;slope field;phase portrait;coupled differential equations|HL",
              hours=(19, 41)),
        ],
    ),
    # ───────────────────────────── Group 4 ─────────────────────────────
    dict(
        key="physics", name="Physics", short="Physics", group=4, levels=["HL", "SL"], syllabus_from=2025, family="science",
        papers=["physics"], books=["group 4 - sciences/physics"], qb=["dp-physics"], qb_paper=["physics"],
        sme=["physics"], sites=["StudyIB/physics"], names=["physics"],
        assessment={
            "SL": [P("Paper 1", 90, 36, "1A: 25 multiple-choice · 1B: data-based questions (20 marks)"),
                   P("Paper 2", 90, 44, "Short-answer and extended-response · 50 marks"),
                   IA("Scientific investigation (IA)", 20, SCI_IA)],
            "HL": [P("Paper 1", 120, 36, "1A: 40 multiple-choice · 1B: data-based questions (20 marks)"),
                   P("Paper 2", 150, 44, "Short-answer and extended-response · 90 marks"),
                   IA("Scientific investigation (IA)", 20, SCI_IA)],
        },
        units=[
            U("A", "Space, time and motion",
              "A.1|Kinematics|kinematics;projectile motion;suvat;displacement;acceleration",
              "A.2|Forces and momentum|newton's laws;momentum;impulse;friction;circular motion",
              "A.3|Work, energy and power|work done;kinetic energy;potential energy;power;efficiency",
              "A.4|Rigid body mechanics|torque;moment of inertia;angular momentum;rotational|HL",
              "A.5|Galilean and special relativity|special relativity;time dilation;length contraction;lorentz|HL",
              hours=(27, 42)),
            U("B", "The particulate nature of matter",
              "B.1|Thermal energy transfers|specific heat capacity;latent heat;conduction;convection;radiation;black body",
              "B.2|Greenhouse effect|greenhouse effect;albedo;emissivity;solar constant",
              "B.3|Gas laws|ideal gas;pressure;boyle;kinetic theory",
              "B.4|Thermodynamics|first law of thermodynamics;entropy;carnot;heat engine|HL",
              "B.5|Current and circuits|resistance;ohm's law;emf;internal resistance;kirchhoff;resistivity",
              hours=(24, 32)),
            U("C", "Wave behaviour",
              "C.1|Simple harmonic motion|simple harmonic motion;oscillation;pendulum;mass-spring",
              "C.2|Wave model|transverse;longitudinal;wavelength;frequency;electromagnetic spectrum",
              "C.3|Wave phenomena|diffraction;interference;refraction;snell's law;double slit",
              "C.4|Standing waves and resonance|standing wave;node;antinode;harmonic;resonance",
              "C.5|Doppler effect|doppler;redshift",
              hours=(17, 29)),
            U("D", "Fields",
              "D.1|Gravitational fields|gravitational field;kepler;orbital;escape speed;gravitational potential",
              "D.2|Electric and magnetic fields|electric field;coulomb's law;magnetic field;electric potential",
              "D.3|Motion in electromagnetic fields|magnetic force;charged particle;lorentz force",
              "D.4|Induction|electromagnetic induction;faraday;lenz;magnetic flux;transformer|HL",
              hours=(19, 38)),
            U("E", "Nuclear and quantum physics",
              "E.1|Structure of the atom|bohr model;emission spectra;energy levels;rutherford scattering",
              "E.2|Quantum physics|photoelectric effect;de broglie;compton;wave-particle duality|HL",
              "E.3|Radioactive decay|half-life;alpha decay;beta decay;binding energy;decay constant",
              "E.4|Fission|nuclear fission;chain reaction;reactor;moderator",
              "E.5|Fusion and stars|nuclear fusion;hertzsprung-russell;stellar evolution;parallax",
              hours=(23, 39)),
            U("T", "Experimental skills and data",
              "T.1|Uncertainties, graphs and data-based questions|uncertainty;error bars;linearisation;significant figures;data-based"),
        ],
    ),
    dict(
        key="chemistry", name="Chemistry", short="Chemistry", group=4, levels=["HL", "SL"], syllabus_from=2025, family="science",
        papers=["chemistry", "chem"], books=["group 4 - sciences/chemistry"], qb=["dp-chemistry"], qb_paper=["chemistry"],
        sme=["chemistry"], sites=["ThinkIB/chem/chemistry", "StudyIB/chemistry"], names=["chemistry"],
        assessment={
            "SL": [P("Paper 1", 90, 36, "1A: 30 multiple-choice · 1B: data-based questions (25 marks)"),
                   P("Paper 2", 90, 44, "Short-answer and extended-response · 50 marks"),
                   IA("Scientific investigation (IA)", 20, SCI_IA)],
            "HL": [P("Paper 1", 120, 36, "1A: 40 multiple-choice · 1B: data-based questions (35 marks)"),
                   P("Paper 2", 150, 44, "Short-answer and extended-response · 90 marks"),
                   IA("Scientific investigation (IA)", 20, SCI_IA)],
        },
        units=[
            U("S1", "Structure 1 · Models of the particulate nature of matter",
              "S1.1|Introduction to the particulate nature of matter|states of matter;mixtures;separation techniques;kinetic molecular theory",
              "S1.2|The nuclear atom|isotopes;mass spectrum;relative atomic mass;subatomic particles",
              "S1.3|Electron configurations|electron configuration;emission spectrum;orbitals;ionization energy",
              "S1.4|Counting particles by mass: the mole|mole;molar mass;empirical formula;concentration;avogadro",
              "S1.5|Ideal gases|ideal gas;molar volume;gas laws;pv=nrt"),
            U("S2", "Structure 2 · Models of bonding and structure",
              "S2.1|The ionic model|ionic bond;lattice;ionic compound",
              "S2.2|The covalent model|covalent bond;lewis structure;vsepr;intermolecular forces;hybridization;resonance",
              "S2.3|The metallic model|metallic bond;delocalized electrons",
              "S2.4|From models to materials|alloys;polymers;bonding triangle;addition polymer"),
            U("S3", "Structure 3 · Classification of matter",
              "S3.1|The periodic table: classification of elements|periodicity;electronegativity;atomic radius;transition elements;oxidation state",
              "S3.2|Functional groups: classification of organic compounds|functional group;homologous series;isomer;iupac nomenclature;spectroscopy"),
            U("R1", "Reactivity 1 · What drives chemical reactions?",
              "R1.1|Measuring enthalpy changes|enthalpy change;calorimetry;exothermic;endothermic",
              "R1.2|Energy cycles in reactions|hess's law;bond enthalpy;born-haber;enthalpy of formation",
              "R1.3|Energy from fuels|combustion;fossil fuels;biofuels;fuel cell",
              "R1.4|Entropy and spontaneity|entropy;gibbs free energy;spontaneity|HL"),
            U("R2", "Reactivity 2 · How much, how fast and how far?",
              "R2.1|How much? The amount of chemical change|limiting reactant;percentage yield;atom economy;stoichiometry",
              "R2.2|How fast? The rate of chemical change|rate of reaction;collision theory;activation energy;rate equation;arrhenius",
              "R2.3|How far? The extent of chemical change|equilibrium;le chatelier;equilibrium constant;reaction quotient"),
            U("R3", "Reactivity 3 · What are the mechanisms of chemical change?",
              "R3.1|Proton transfer reactions|acid;base;ph;buffer;titration;ka;kw",
              "R3.2|Electron transfer reactions|redox;oxidation;reduction;electrochemical cell;electrolysis;standard electrode potential",
              "R3.3|Electron sharing reactions|radical;homolytic fission;free radical substitution",
              "R3.4|Electron-pair sharing reactions|nucleophile;electrophile;nucleophilic substitution;electrophilic addition;lewis acid"),
            U("T", "Experimental skills and data",
              "T.1|Practical techniques, uncertainties and data-based questions|uncertainty;titration technique;graphing;data-based;percentage error"),
        ],
    ),
    dict(
        key="biology", name="Biology", short="Biology", group=4, levels=["HL", "SL"], syllabus_from=2025, family="science",
        papers=["biology"], books=["group 4 - sciences/biology"], qb=["dp-biology"], qb_paper=["biology"],
        sme=["biology"], sites=["ThinkIB/bio_psych/biology", "StudyIB/biology", "TeachMe Biology"], names=["biology"],
        assessment={
            "SL": [P("Paper 1", 90, 36, "1A: 30 multiple-choice · 1B: data-based questions (25 marks)"),
                   P("Paper 2", 90, 44, "Data-based, short-answer and extended-response · 50 marks"),
                   IA("Scientific investigation (IA)", 20, SCI_IA)],
            "HL": [P("Paper 1", 120, 36, "1A: 40 multiple-choice · 1B: data-based questions (35 marks)"),
                   P("Paper 2", 150, 44, "Data-based, short-answer and extended-response · 80 marks"),
                   IA("Scientific investigation (IA)", 20, SCI_IA)],
        },
        units=[
            U("A", "Unity and diversity",
              "A1.1|Water|water;hydrogen bonding;cohesion;solvent",
              "A1.2|Nucleic acids|dna structure;nucleotide;rna;base pairing",
              "A2.1|Origins of cells|origin of life;miller-urey;luca;protocell|HL",
              "A2.2|Cell structure|prokaryote;eukaryote;organelle;microscopy;cell theory",
              "A2.3|Viruses|virus;lytic cycle;lysogenic;bacteriophage|HL",
              "A3.1|Diversity of organisms|species;binomial nomenclature;karyotype;genome",
              "A3.2|Classification and cladistics|cladogram;clade;taxonomy|HL",
              "A4.1|Evolution and speciation|evolution;speciation;homologous structures;selective breeding",
              "A4.2|Conservation of biodiversity|biodiversity;extinction;conservation;simpson's index"),
            U("B", "Form and function",
              "B1.1|Carbohydrates and lipids|carbohydrate;lipid;polysaccharide;fatty acid;triglyceride",
              "B1.2|Proteins|amino acid;polypeptide;protein structure;denaturation",
              "B2.1|Membranes and membrane transport|phospholipid bilayer;diffusion;osmosis;active transport;fluid mosaic",
              "B2.2|Organelles and compartmentalization|organelle;compartmentalization;mitochondria;chloroplast",
              "B2.3|Cell specialization|stem cell;differentiation;surface area to volume",
              "B3.1|Gas exchange|gas exchange;alveoli;stomata;ventilation;haemoglobin",
              "B3.2|Transport|blood vessels;heart;xylem;phloem;transpiration",
              "B3.3|Muscle and motility|sarcomere;muscle contraction;actin;myosin;skeleton|HL",
              "B4.1|Adaptation to environment|habitat;adaptation;biome;abiotic",
              "B4.2|Ecological niches|niche;autotroph;heterotroph;competitive exclusion"),
            U("C", "Interaction and interdependence",
              "C1.1|Enzymes and metabolism|enzyme;active site;activation energy;inhibition;metabolism",
              "C1.2|Cell respiration|respiration;atp;glycolysis;krebs cycle;electron transport chain",
              "C1.3|Photosynthesis|photosynthesis;chlorophyll;light-dependent;calvin cycle;limiting factors",
              "C2.1|Chemical signalling|receptor;ligand;hormone;signal transduction;second messenger|HL",
              "C2.2|Neural signalling|neuron;action potential;synapse;neurotransmitter",
              "C3.1|Integration of body systems|nervous system;reflex arc;hormone;feedback;tropism",
              "C3.2|Defence against disease|pathogen;antibody;immune;vaccination;antibiotic",
              "C4.1|Populations and communities|population;carrying capacity;predator-prey;competition;sampling",
              "C4.2|Transfers of energy and matter|food chain;trophic level;carbon cycle;energy pyramid"),
            U("D", "Continuity and change",
              "D1.1|DNA replication|dna replication;helicase;dna polymerase;pcr;gel electrophoresis",
              "D1.2|Protein synthesis|transcription;translation;codon;ribosome;mrna",
              "D1.3|Mutations and gene editing|mutation;crispr;gene knockout;mutagen",
              "D2.1|Cell and nuclear division|mitosis;meiosis;cytokinesis;cell cycle;non-disjunction",
              "D2.2|Gene expression|gene expression;epigenetics;methylation;transcription factor|HL",
              "D2.3|Water potential|water potential;osmosis;turgor;hypertonic",
              "D3.1|Reproduction|sexual reproduction;menstrual cycle;fertilization;pollination",
              "D3.2|Inheritance|punnett;allele;genotype;phenotype;sex linkage;pedigree",
              "D3.3|Homeostasis|homeostasis;blood glucose;insulin;thermoregulation;kidney;osmoregulation",
              "D4.1|Natural selection|natural selection;fitness;sexual selection;hardy-weinberg",
              "D4.2|Stability and change|ecosystem stability;tipping point;succession;eutrophication;rewilding",
              "D4.3|Climate change|climate change;greenhouse;carbon sequestration;phenology;ocean acidification"),
            U("T", "Experimental skills and data",
              "T.1|Data-based questions and experimental skills|data-based;error bars;statistical test;graph interpretation;t-test"),
        ],
    ),
    dict(
        key="ess", name="Environmental Systems and Societies", short="ESS", group=4, levels=["HL", "SL"], syllabus_from=2026, family="science",
        papers=["environmental systems and societies", "ess"], books=["group 4 - sciences/environmental systems and societies"],
        qb=["dp-environmental-systems-and-societies"], qb_paper=["ess", "environmental systems"],
        sme=["ess"], sites=[], names=["environmental systems and societies"],
        assessment={
            "SL": [P("Paper 1", 60, 25, "Case study with resource booklet"), P("Paper 2", 120, 50, "Short answers and structured essays"),
                   IA("Individual investigation (IA)", 25, "Research question on an environmental issue; max 3,000 words.")],
            "HL": [P("Paper 1", 120, 30, "Case study with resource booklet"), P("Paper 2", 150, 50, "Short answers and structured essays"),
                   IA("Individual investigation (IA)", 20, "Research question on an environmental issue; max 3,000 words.")],
        },
        units=[
            U("1", "Foundation", "1.1|Perspectives|worldview;value system;environmental perspective", "1.2|Systems|systems;feedback;equilibrium;tipping point;model", "1.3|Sustainability|sustainability;ecological footprint;planetary boundaries;circular economy"),
            U("2", "Ecology", "2.1|Individuals, populations, communities and ecosystems|niche;population;carrying capacity;ecosystem", "2.2|Energy and biomass in ecosystems|productivity;trophic level;food web;pyramid", "2.3|Biogeochemical cycles|carbon cycle;nitrogen cycle", "2.4|Climate and biomes|biome;climate;tricellular model", "2.5|Zonation, succession and change in ecosystems|succession;zonation;climax community"),
            U("3", "Biodiversity and conservation", "3.1|Biodiversity and evolution|biodiversity;speciation;natural selection", "3.2|Human impact on biodiversity|extinction;habitat loss;invasive species;red list", "3.3|Conservation and regeneration|conservation;protected area;rewilding;cites"),
            U("4", "Water", "4.1|Water systems|hydrological cycle;ocean circulation", "4.2|Water access, use and security|water security;water scarcity;irrigation", "4.3|Aquatic food production systems|fisheries;aquaculture;maximum sustainable yield", "4.4|Water pollution|eutrophication;biochemical oxygen demand;water pollution"),
            U("5", "Land", "5.1|Soil|soil profile;soil texture;soil fertility", "5.2|Agriculture and food|agriculture;food production;sustainable farming", ),
            U("6", "Atmosphere and climate change", "6.1|Introduction to the atmosphere|atmosphere;greenhouse effect", "6.2|Climate change: causes and impacts|climate change;global warming;sea level", "6.3|Climate change: mitigation and adaptation|mitigation;adaptation;geoengineering", "6.4|Stratospheric ozone|ozone;cfc;montreal protocol"),
            U("7", "Natural resources", "7.1|Natural resources: uses and management|natural capital;resource management", "7.2|Energy sources: uses and management|renewable;fossil fuel;energy security", "7.3|Solid waste|waste;landfill;recycling"),
            U("8", "Human populations and urban systems", "8.1|Human populations|demographic transition;population pyramid;fertility rate", "8.2|Urban systems and urban planning|urbanization;urban planning", "8.3|Urban air pollution|smog;acid rain;particulate"),
            U("HL", "HL lenses", "HL.a|Environmental law|environmental law;legislation|HL", "HL.b|Environmental economics|externality;ecological economics;green gdp|HL", "HL.c|Environmental ethics|environmental ethics;intrinsic value|HL"),
        ],
    ),
    dict(
        key="computer_science", name="Computer Science", short="Comp Sci", group=4, levels=["HL", "SL"], syllabus_from=2014, family="science",
        papers=["computer science", "compsci", "cs"], books=["group 4 - sciences/computer science"], qb=["dp-computer-science"], qb_paper=["computer science"],
        sme=["computer science"], sites=[], names=["computer science"],
        note="A new Computer Science course is examined from 2027. If your exams are in 2027 or later, check the topic list with your teacher and edit topics on this page.",
        assessment={
            "SL": [P("Paper 1", 90, 45, "Core topics · 70 marks"), P("Paper 2", 60, 25, "Option · 45 marks"), IA("Solution (IA)", 30, "Computational solution with documentation and video.")],
            "HL": [P("Paper 1", 130, 40, "Core + HL extension · 100 marks"), P("Paper 2", 80, 20, "Option · 65 marks"), P("Paper 3", 60, 20, "Pre-released case study · 30 marks"), IA("Solution (IA)", 20, "Computational solution with documentation and video.")],
        },
        units=[
            U("1", "System fundamentals", "1.1|Systems in organizations|system life cycle;stakeholders;data migration;testing", "1.2|System design basics|usability;ergonomics;prototype;hardware and software"),
            U("2", "Computer organization", "2.1|Computer architecture and binary|cpu;fetch-execute;binary;hexadecimal;logic gates;truth table;primary memory"),
            U("3", "Networks", "3.1|Networks|lan;wan;osi model;protocol;packet switching;vpn;wireless"),
            U("4", "Computational thinking, problem-solving and programming", "4.1|General principles of computational thinking|thinking procedurally;abstraction;concurrent", "4.2|Connecting computational thinking and program design|flowchart;pseudocode;linear search;binary search;bubble sort;selection sort;big o", "4.3|Introduction to programming|variables;loops;arrays;collections;trace table"),
            U("5", "Abstract data structures", "5.1|Abstract data structures|recursion;stack;queue;linked list;binary tree;two-dimensional array|HL"),
            U("6", "Resource management", "6.1|Resource management|operating system;scheduling;virtual memory;paging|HL"),
            U("7", "Control", "7.1|Control systems|sensor;actuator;feedback;embedded system;distributed systems|HL"),
            U("O", "Option (choose one)", "A|Databases|database;sql;normalization;relational;transaction|OPT", "B|Modelling and simulation|simulation;model;visualization|OPT", "C|Web science|web;search engine;html;cloud;semantic web|OPT", "D|Object-oriented programming|class;object;inheritance;polymorphism;encapsulation|ON"),
        ],
    ),
    dict(
        key="sehs", name="Sports, Exercise and Health Science", short="SEHS", group=4, levels=["HL", "SL"], syllabus_from=2026, family="science",
        papers=["sports exercise and health science", "sehs"], books=["group 4 - sciences/sports, exercise and health science"], qb=["dp-sports-exercise-and-health-science"], qb_paper=["sehs", "sports"],
        sme=["sehs", "sports"], sites=[], names=["sports, exercise and health science", "sports exercise and health science"],
        assessment={
            "SL": [P("Paper 1", 90, 36, "1A multiple-choice · 1B data-based"), P("Paper 2", 90, 44, "Short-answer and extended-response"), IA("Scientific investigation (IA)", 20, SCI_IA)],
            "HL": [P("Paper 1", 105, 36, "1A multiple-choice · 1B data-based"), P("Paper 2", 150, 44, "Short-answer and extended-response"), IA("Scientific investigation (IA)", 20, SCI_IA)],
        },
        units=[
            U("A", "Exercise physiology and nutrition of the human body", "A.1|Communication|nervous system;endocrine;homeostasis", "A.2|Hydration and nutrition|nutrition;hydration;macronutrient;energy systems", "A.3|Response|training adaptation;fatigue;recovery;cardiovascular drift"),
            U("B", "Biomechanics", "B.1|Generating movement in the body|muscle;joint;lever;anatomy", "B.2|Forces, motion and movement|newton;momentum;projectile;angular", "B.3|Injury|injury;rehabilitation;overuse"),
            U("C", "Sports psychology and motor learning", "C.1|Individual differences|personality;motivation;mental toughness", "C.2|Motor learning|motor learning;skill acquisition;feedback;information processing", "C.3|Motivation|motivation;self-determination;goal setting", "C.4|Stress and coping|arousal;anxiety;stress;coping", "C.5|Psychological skills|imagery;self-talk;relaxation"),
        ],
    ),
    dict(
        key="design_technology", name="Design Technology", short="Design Tech", group=4, levels=["HL", "SL"], syllabus_from=2016, family="science",
        papers=["design technology"], books=["group 4 - sciences/design technology"], qb=["dp-design-technology"], qb_paper=["design technology"],
        sme=["design"], sites=[], names=["design technology"],
        assessment={
            "SL": [P("Paper 1", 45, 30, "30 multiple-choice"), P("Paper 2", 90, 30, "Data-based and extended-response"), IA("Design project (IA)", 40, "Design project.")],
            "HL": [P("Paper 1", 60, 20, "40 multiple-choice"), P("Paper 2", 90, 20, "Data-based and extended-response"), P("Paper 3", 90, 20, "HL extension, case study"), IA("Design project (IA)", 40, "Design project.")],
        },
        units=[
            U("C", "Core", "1|Human factors and ergonomics|anthropometrics;ergonomics;percentile", "2|Resource management and sustainable production|sustainable;recycling;clean technology;green design", "3|Modelling|prototype;cad;conceptual model;rapid prototyping", "4|Final production|materials;manufacturing processes;timber;metals;plastics;composites", "5|Innovation and design|invention;innovation;product life cycle;rogers", "6|Classic design|classic design;form versus function"),
            U("H", "HL extension", "7|User-centred design|user-centred;usability;persona|HL", "8|Sustainability|triple bottom line;sustainable design|HL", "9|Innovation and markets|market;branding;pricing|HL", "10|Commercial production|just in time;lean production;quality control|HL"),
        ],
    ),
    # ───────────────────────────── Group 3 ─────────────────────────────
    dict(
        key="economics", name="Economics", short="Economics", group=3, levels=["HL", "SL"], syllabus_from=2022, family="humanities",
        papers=["economics", "econ"], books=["group 3 - individuals and societies/economics"], qb=["dp-economics"], qb_paper=["economics"],
        sme=["economics"], sites=["ThinkIB/bm_econ/economics"], names=["economics"],
        assessment={
            "SL": [P("Paper 1", 75, 30, "Extended response (10 + 15 marks) · choose 1 of 3"),
                   P("Paper 2", 105, 40, "Data response · choose 1 of 2 · 40 marks"),
                   IA("Portfolio of three commentaries (IA)", 30, "Three commentaries (max 800 words each) on news articles, each through a different key concept.")],
            "HL": [P("Paper 1", 75, 20, "Extended response (10 + 15 marks) · choose 1 of 3"),
                   P("Paper 2", 105, 30, "Data response · choose 1 of 2 · 40 marks"),
                   P("Paper 3", 105, 30, "Policy paper · quantitative + 10-mark policy recommendation · 60 marks"),
                   IA("Portfolio of three commentaries (IA)", 20, "Three commentaries (max 800 words each) on news articles.")],
        },
        units=[
            U("1", "Introduction to economics", "1.1|What is economics?|scarcity;opportunity cost;production possibilities curve;circular flow", "1.2|How do economists approach the world?|positive and normative;economic methodology;economic thought"),
            U("2", "Microeconomics",
              "2.1|Demand|law of demand;demand curve;determinants of demand", "2.2|Supply|law of supply;supply curve", "2.3|Competitive market equilibrium|equilibrium;consumer surplus;producer surplus;allocative efficiency",
              "2.4|Critique of the maximizing behaviour of consumers and producers|behavioural economics;nudge;bounded rationality;corporate social responsibility",
              "2.5|Elasticities of demand|price elasticity of demand;income elasticity;ped;yed", "2.6|Elasticity of supply|price elasticity of supply;pes",
              "2.7|Role of government in microeconomics|price ceiling;price floor;indirect tax;subsidy", "2.8|Market failure: externalities and common pool resources|externality;merit good;demerit good;carbon tax;tradable permits;common pool",
              "2.9|Market failure: public goods|public good;free rider", "2.10|Market failure: asymmetric information|asymmetric information;adverse selection;moral hazard|HL",
              "2.11|Market failure: market power|monopoly;oligopoly;perfect competition;monopolistic competition;game theory;marginal cost|HL", "2.12|The market's inability to achieve equity|equity;inequality|HL"),
            U("3", "Macroeconomics",
              "3.1|Measuring economic activity|gdp;gni;business cycle;real gdp", "3.2|Variations in economic activity: AD and AS|aggregate demand;aggregate supply;keynesian;inflationary gap;multiplier",
              "3.3|Macroeconomic objectives|economic growth;unemployment;inflation;deflation;phillips curve", "3.4|Economics of inequality and poverty|lorenz curve;gini;poverty;progressive tax",
              "3.5|Demand management: monetary policy|monetary policy;interest rate;central bank;money supply", "3.6|Demand management: fiscal policy|fiscal policy;government spending;crowding out;automatic stabilizers",
              "3.7|Supply-side policies|supply-side;market-based;interventionist"),
            U("4", "The global economy",
              "4.1|Benefits of international trade|comparative advantage;free trade;absolute advantage", "4.2|Types of trade protection|tariff;quota;export subsidy;administrative barriers",
              "4.3|Arguments for and against trade protection|infant industry;dumping;protectionism", "4.4|Economic integration|trading bloc;customs union;common market;wto;monetary union",
              "4.5|Exchange rates|exchange rate;appreciation;depreciation;floating;fixed exchange rate", "4.6|Balance of payments|current account;financial account;marshall-lerner;j-curve",
              "4.7|Sustainable development|sustainable development goals;sustainability", "4.8|Measuring development|hdi;development indicators;composite indicator",
              "4.9|Barriers to economic growth and development|poverty trap;barriers to development;indebtedness", "4.10|Economic growth and development strategies|foreign aid;fdi;microfinance;import substitution;export promotion"),
            U("S", "Exam skills", "S.1|Diagrams, definitions and real-world examples bank|diagram;real-world example;evaluation;clasp", "S.2|Paper 3 quantitative methods and policy recommendation|calculate;policy recommendation;quantitative|HL"),
        ],
    ),
    dict(
        key="business_management", name="Business Management", short="Business", group=3, levels=["HL", "SL"], syllabus_from=2024, family="humanities",
        papers=["business management", "business and management", "bm"], books=["group 3 - individuals and societies/business management"],
        qb=["dp-business-management"], qb_paper=["business management"],
        sme=["business management"], sites=["ThinkIB/bm_econ/businessmanagement", "Lewwinski Business Management", "IB Biz (BM Case Studies)"], names=["business management"],
        assessment={
            "SL": [P("Paper 1", 90, 35, "Based on a pre-released statement · 30 marks"), P("Paper 2", 90, 35, "Quantitative focus, stimulus material · 40 marks"),
                   IA("Business research project (IA)", 30, "Max 1,800 words, 3–5 supporting documents, one key concept (change, creativity, ethics or sustainability).")],
            "HL": [P("Paper 1", 90, 25, "Based on a pre-released statement · 30 marks"), P("Paper 2", 105, 30, "Quantitative focus, stimulus material · 50 marks"),
                   P("Paper 3", 75, 25, "Social enterprise case · 25 marks"),
                   IA("Business research project (IA)", 20, "Max 1,800 words, 3–5 supporting documents, one key concept.")],
        },
        units=[
            U("1", "Introduction to business management", "1.1|What is a business?|sectors;entrepreneurship;business functions", "1.2|Types of business entities|sole trader;partnership;corporation;social enterprise;cooperative", "1.3|Business objectives|vision;mission;swot;ansoff;csr", "1.4|Stakeholders|stakeholder;stakeholder conflict", "1.5|Growth and evolution|economies of scale;merger;franchise;joint venture", "1.6|Multinational companies|multinational;mnc;host country"),
            U("2", "Human resource management", "2.1|Introduction to human resource management|workforce planning;labour turnover;demographic change", "2.2|Organizational structure|span of control;delegation;hierarchy;matrix structure", "2.3|Leadership and management|leadership style;autocratic;democratic;laissez-faire", "2.4|Motivation and demotivation|maslow;herzberg;taylor;motivation;financial rewards;training;appraisal", "2.5|Organizational (corporate) culture|corporate culture;handy;culture clash|HL", "2.6|Communication|communication;barriers to communication", "2.7|Industrial/employee relations|trade union;collective bargaining;conflict resolution|HL"),
            U("3", "Finance and accounts", "3.1|Introduction to finance|capital expenditure;revenue expenditure", "3.2|Sources of finance|sources of finance;share capital;loan;crowdfunding", "3.3|Costs and revenues|fixed cost;variable cost;revenue streams", "3.4|Final accounts|balance sheet;profit and loss;statement of financial position;depreciation", "3.5|Profitability and liquidity ratio analysis|gross profit margin;current ratio;roce;acid test", "3.6|Debt/equity ratio analysis|gearing;debtor days;stock turnover;insolvency|HL", "3.7|Cash flow|cash flow forecast;working capital", "3.8|Investment appraisal|payback period;average rate of return;net present value", "3.9|Budgets|budget;variance analysis;cost centre|HL"),
            U("4", "Marketing", "4.1|Introduction to marketing|market orientation;market share;market growth", "4.2|Marketing planning|segmentation;targeting;positioning;usp;marketing mix", "4.3|Sales forecasting|sales forecasting;moving average;time series|HL", "4.4|Market research|primary research;secondary research;sampling", "4.5|The seven Ps of the marketing mix|product life cycle;bcg matrix;pricing;promotion;place;branding", "4.6|International marketing|international marketing;globalization|HL"),
            U("5", "Operations management", "5.1|Introduction to operations management|operations", "5.2|Operations methods|job production;batch production;mass production;mass customization", "5.3|Lean production and quality management|lean;kaizen;just in time;quality assurance;benchmarking|HL", "5.4|Location|location;outsourcing;offshoring", "5.5|Break-even analysis|break-even;contribution;margin of safety", "5.6|Production planning|supply chain;stock control;capacity utilization;productivity|HL", "5.7|Crisis management and contingency planning|crisis management;contingency plan|HL", "5.8|Research and development|research and development;innovation|HL", "5.9|Management information systems|big data;data analytics;cybersecurity;artificial intelligence|HL"),
            U("K", "Toolkit, concepts and case study", "K.1|Business management toolkit|swot;ansoff;steeple;bcg;decision tree;force field;gantt;porter", "K.2|Key concepts and pre-released case study|change;creativity;ethics;sustainability;case study"),
        ],
    ),
    dict(
        key="history", name="History", short="History", group=3, levels=["HL", "SL"], syllabus_from=2017, family="humanities",
        papers=["history", "history route 2"], books=["group 3 - individuals and societies/history"], qb=["dp-history"], qb_paper=["history"],
        sme=["history"], sites=["ThinkIB/history"], names=["history"],
        note="History topics depend on what your school teaches. Tick the prescribed subject, world history topics and HL region you actually study.",
        assessment={
            "SL": [P("Paper 1", 60, 30, "Source-based paper on one prescribed subject · 24 marks"), P("Paper 2", 90, 45, "Two essays on two world history topics · 30 marks"),
                   IA("Historical investigation (IA)", 25, "Max 2,200 words: source evaluation, investigation, reflection.")],
            "HL": [P("Paper 1", 60, 20, "Source-based paper on one prescribed subject · 24 marks"), P("Paper 2", 90, 25, "Two essays on two world history topics · 30 marks"),
                   P("Paper 3", 150, 35, "Three essays on your regional option · 45 marks"),
                   IA("Historical investigation (IA)", 20, "Max 2,200 words.")],
        },
        units=[
            U("P1", "Paper 1 · Prescribed subject (study one)", "PS1|Military leaders|genghis khan;richard i|OPT", "PS2|Conquest and its impact|conquest of mexico;granada|OPT", "PS3|The move to global war|japanese expansion;manchuria;abyssinia;appeasement;hitler foreign policy|ON", "PS4|Rights and protest|civil rights movement;apartheid;martin luther king;mandela|OPT", "PS5|Conflict and intervention|rwanda;kosovo|OPT"),
            U("P2", "Paper 2 · World history topics (study two)", "WH7|Origins, development and impact of industrialization|industrialization|OPT", "WH8|Independence movements (1800–2000)|independence movement;decolonization|OPT", "WH9|Emergence and development of democratic states|democratic state;weimar|OPT", "WH10|Authoritarian states (20th century)|authoritarian;hitler;mao;stalin;castro;mussolini|ON", "WH11|Causes and effects of 20th-century wars|first world war;second world war;causes of war;total war|OPT", "WH12|The Cold War: superpower tensions and rivalries|cold war;containment;detente;cuban missile crisis|ON"),
            U("P3", "Paper 3 · HL regional option (study one)", "R1|History of Africa and the Middle East|africa;middle east|HL OPT", "R2|History of the Americas|americas;united states;latin america|HL OPT", "R3|History of Asia and Oceania|asia;china;japan;india|HL OPT", "R4|History of Europe|europe;russia;germany;italy|HL ON"),
            U("S", "Skills", "S.1|Source analysis (origin, purpose, value, limitation)|opvl;source analysis;value and limitations", "S.2|Essay technique and historiography|essay structure;historiography;thesis"),
        ],
    ),
    dict(
        key="geography", name="Geography", short="Geography", group=3, levels=["HL", "SL"], syllabus_from=2019, family="humanities",
        papers=["geography"], books=["group 3 - individuals and societies/geography"], qb=["dp-geography"], qb_paper=["geography"],
        sme=["geography"], sites=[], names=["geography"],
        note="Tick the optional themes your school teaches (SL: two, HL: three).",
        assessment={
            "SL": [P("Paper 1", 90, 35, "Two optional themes · 40 marks"), P("Paper 2", 75, 40, "Core units · 50 marks"), IA("Fieldwork report (IA)", 25, "Max 2,500 words.")],
            "HL": [P("Paper 1", 135, 35, "Three optional themes · 60 marks"), P("Paper 2", 75, 25, "Core units · 50 marks"), P("Paper 3", 60, 20, "HL core extension · 28 marks"), IA("Fieldwork report (IA)", 20, "Max 2,500 words.")],
        },
        units=[
            U("O", "Paper 1 · Optional themes", "A|Freshwater|drainage basin;flooding;water scarcity|OPT", "B|Oceans and coastal margins|coastal;ocean;coral reef|OPT", "C|Extreme environments|desert;periglacial;arid|OPT", "D|Geophysical hazards|earthquake;volcano;mass movement|ON", "E|Leisure, tourism and sport|tourism;leisure|OPT", "F|Food and health|food security;disease;famine|OPT", "G|Urban environments|urbanization;urban stress;megacity|ON"),
            U("C", "Paper 2 · Core: global change", "1|Changing population|population distribution;demographic transition;migration", "2|Global climate: vulnerability and resilience|climate change;enhanced greenhouse effect;mitigation", "3|Global resource consumption and security|water-food-energy nexus;resource security;ecological footprint"),
            U("H", "Paper 3 · HL extension: global interactions", "4|Power, places and networks|globalization;superpower;tnc|HL", "5|Human development and diversity|human development;cultural diffusion;sdg|HL", "6|Global risks and resilience|global risk;hacking;resilience|HL"),
            U("S", "Skills", "S.1|Infographic, map and data skills|infographic;choropleth;graph interpretation"),
        ],
    ),
    dict(
        key="psychology", name="Psychology", short="Psychology", group=3, levels=["HL", "SL"], syllabus_from=2019, family="humanities",
        papers=["psychology"], books=["group 3 - individuals and societies/psychology"], qb=["dp-psychology"], qb_paper=["psychology"],
        sme=["psychology"], sites=["ThinkIB/bio_psych/psychology"], names=["psychology"],
        note="A new Psychology course is examined from 2027. If your exams are in 2027 or later, confirm the topic list with your teacher and edit topics on this page.",
        assessment={
            "SL": [P("Paper 1", 120, 50, "Three short answers + one essay on the core approaches · 49 marks"), P("Paper 2", 60, 25, "One essay on one option · 22 marks"), IA("Experimental study (IA)", 25, "1,800–2,200 words: introduction, exploration, analysis, evaluation.")],
            "HL": [P("Paper 1", 120, 40, "Three short answers + one essay incl. HL extensions · 49 marks"), P("Paper 2", 120, 20, "Two essays on two options · 44 marks"), P("Paper 3", 60, 20, "Research methods questions on a stimulus · 24 marks"), IA("Experimental study (IA)", 20, "1,800–2,200 words.")],
        },
        units=[
            U("C", "Core approaches", "BIO|Biological approach|brain and behaviour;neuroplasticity;hormones;genetics;localization", "COG|Cognitive approach|memory models;schema theory;thinking and decision making;reconstructive memory;emotion and cognition", "SOC|Sociocultural approach|social identity theory;social cognitive theory;stereotypes;cultural dimensions;acculturation", "RM|Research methodology and ethics|experiment;validity;sampling;ethics;qualitative research"),
            U("O", "Options", "ABN|Abnormal psychology|depression;diagnosis;etiology;treatment|ON", "DEV|Developmental psychology|attachment;cognitive development;piaget|OPT", "HEA|Health psychology|stress;obesity;health promotion|OPT", "REL|Psychology of human relationships|attraction;bystander;prejudice;cooperation|OPT"),
            U("S", "Skills", "S.1|Studies bank and essay structure|aim;procedure;findings;evaluate;critical thinking"),
        ],
    ),
    dict(
        key="global_politics", name="Global Politics", short="Global Politics", group=3, levels=["HL", "SL"], syllabus_from=2026, family="humanities",
        papers=["global politics"], books=["group 3 - individuals and societies/global politics"], qb=[], qb_paper=[],
        sme=["global politics"], sites=[], names=["global politics"],
        assessment={
            "SL": [P("Paper 1", 75, 30, "Source-based questions"), P("Paper 2", 105, 40, "Two essays"), IA("Engagement project (IA)", 30, "Report on a political issue explored through engagement.")],
            "HL": [P("Paper 1", 75, 20, "Source-based questions"), P("Paper 2", 105, 30, "Two essays"), P("Paper 3", 90, 30, "Stimulus-based paper on global political challenges"), IA("Engagement project (IA)", 20, "Report on a political issue explored through engagement.")],
        },
        units=[
            U("C", "Core", "C.1|Understanding power and global politics|power;sovereignty;legitimacy;interdependence;realism;liberalism"),
            U("T", "Thematic studies", "T.1|Rights and justice|human rights;justice;universal declaration", "T.2|Development and sustainability|development;sustainability;inequality", "T.3|Peace and conflict|peace;conflict;violence;peacebuilding"),
            U("H", "HL extension", "H.1|Global political challenges (case studies)|case study;security;environment;poverty;health;identity;borders;technology;equality|HL"),
        ],
    ),
    dict(
        key="philosophy", name="Philosophy", short="Philosophy", group=3, levels=["HL", "SL"], syllabus_from=2016, family="humanities",
        papers=["philosophy"], books=["group 3 - individuals and societies/philosophy"], qb=[], qb_paper=[], sme=["philosophy"], sites=[], names=["philosophy"],
        assessment={
            "SL": [P("Paper 1", 105, 50, "Core theme + one optional theme"), P("Paper 2", 60, 25, "Prescribed text"), IA("Philosophical analysis (IA)", 25, "Analysis of a non-philosophical stimulus.")],
            "HL": [P("Paper 1", 150, 40, "Core theme + two optional themes"), P("Paper 2", 60, 20, "Prescribed text"), P("Paper 3", 75, 20, "Unseen text on philosophical activity"), IA("Philosophical analysis (IA)", 20, "Analysis of a non-philosophical stimulus.")],
        },
        units=[
            U("C", "Core", "C.1|Being human|personhood;mind and body;freedom;identity;human nature"),
            U("O", "Optional themes", "O.1|Ethics|normative ethics;utilitarianism;deontology;virtue ethics|ON", "O.2|Epistemology|knowledge;scepticism;rationalism;empiricism|OPT", "O.3|Political philosophy|justice;liberty;rights;state|OPT", "O.4|Philosophy of religion|existence of god;problem of evil|OPT", "O.5|Aesthetics / other theme|aesthetics;art|OPT"),
            U("T", "Texts and HL", "T.1|Prescribed text|prescribed text", "T.2|HL: Exploring philosophical activity|philosophical activity|HL"),
        ],
    ),
    dict(
        key="digital_society", name="Digital Society", short="Digital Society", group=3, levels=["HL", "SL"], syllabus_from=2024, family="humanities",
        papers=["digital society"], papers_legacy=[("itgs", "Old course (ITGS)"), ("information technology in a global society", "Old course (ITGS)")],
        books=["group 3 - individuals and societies/digital society", "group 3 - individuals and societies/itgs"], qb=["dp-digital-society"], qb_paper=["digital society"],
        sme=["digital society"], sites=[], names=["digital society", "information technology in a global society"],
        assessment={
            "SL": [P("Paper 1", 90, 40, "Structured questions"), P("Paper 2", 75, 30, "Source-based questions"), IA("Inquiry project (IA)", 30, "Inquiry into impacts of a digital system.")],
            "HL": [P("Paper 1", 135, 35, "Structured questions incl. HL extension"), P("Paper 2", 75, 20, "Source-based questions"), P("Paper 3", 75, 25, "Pre-released brief on an intervention"), IA("Inquiry project (IA)", 20, "Inquiry into impacts of a digital system.")],
        },
        units=[
            U("1", "Concepts", "2.1-2.7|Change, expression, identity, power, space, systems, values and ethics|change;expression;identity;power;space;systems;values and ethics"),
            U("2", "Content", "3.1|Data|data;big data;privacy", "3.2|Algorithms|algorithm;bias", "3.3|Computers|hardware;software", "3.4|Networks and the internet|network;internet;cloud", "3.5|Media|digital media;deepfake", "3.6|Artificial intelligence|artificial intelligence;machine learning", "3.7|Robots and autonomous technologies|robot;autonomous"),
            U("3", "Contexts", "4.1-4.7|Cultural, economic, environmental, health, human knowledge, political, social|cultural;economic;environmental;health;political;social"),
            U("H", "HL extension", "5|Challenges and interventions|global well-being;governance and human rights;sustainable development;intervention|HL"),
        ],
    ),
    # ───────────────────────────── Group 6 ─────────────────────────────
    dict(
        key="visual_arts", name="Visual Arts", short="Visual Arts", group=6, levels=["HL", "SL"], syllabus_from=2017, family="arts",
        papers=["visual arts"], books=["group 6 - the arts/visual arts"], qb=[], qb_paper=[], sme=[], sites=["ThinkIB/chem/visualarts"], names=["visual arts"],
        assessment={"SL": [IA("Comparative study", 20), IA("Process portfolio", 40), IA("Exhibition", 40)], "HL": [IA("Comparative study", 20), IA("Process portfolio", 40), IA("Exhibition", 40)]},
        units=[U("1", "Coursework", "1|Comparative study|comparative study;formal qualities", "2|Process portfolio|process portfolio;experimentation", "3|Exhibition|exhibition;curatorial rationale")],
    ),
    dict(
        key="music", name="Music", short="Music", group=6, levels=["HL", "SL"], syllabus_from=2022, family="arts",
        papers=["music"], books=["group 6 - the arts/music"], qb=[], qb_paper=[], sme=[], sites=[], names=["music"],
        assessment={"SL": [IA("Exploring music in context", 30), IA("Experimenting with music", 30), IA("Presenting music", 40)], "HL": [IA("Exploring music in context", 20), IA("Experimenting with music", 20), IA("Presenting music", 30), IA("The contemporary music maker", 30)]},
        units=[U("1", "Coursework", "1|Exploring music in context|areas of inquiry;musical analysis", "2|Experimenting with music|experimentation", "3|Presenting music|performance;composition", "4|The contemporary music maker|collaborative project|HL")],
    ),
    dict(
        key="theatre", name="Theatre", short="Theatre", group=6, levels=["HL", "SL"], syllabus_from=2024, family="arts",
        papers=["theatre"], books=[], qb=[], qb_paper=[], sme=[], sites=[], names=["theatre"],
        assessment={"SL": [IA("Production proposal", 30), IA("Research presentation", 30), IA("Collaborative project", 40)], "HL": [IA("Production proposal", 20), IA("Research presentation", 20), IA("Collaborative project", 25), IA("Solo theatre piece", 35)]},
        units=[U("1", "Coursework", "1|Production proposal|production proposal", "2|Research presentation|theatre tradition", "3|Collaborative project|collaborative", "4|Solo theatre piece|theatre theorist|HL")],
    ),
    dict(
        key="film", name="Film", short="Film", group=6, levels=["HL", "SL"], syllabus_from=2019, family="arts",
        papers=["film"], books=[], qb=[], qb_paper=[], sme=[], sites=[], names=["film"],
        assessment={"SL": [IA("Textual analysis", 30), IA("Comparative study", 30), IA("Film portfolio", 40)], "HL": [IA("Textual analysis", 20), IA("Comparative study", 20), IA("Film portfolio", 25), IA("Collaborative film project", 35)]},
        units=[U("1", "Coursework", "1|Textual analysis|film elements;cinematography", "2|Comparative study|comparative study", "3|Film portfolio|film production roles", "4|Collaborative film project|collaborative film|HL")],
    ),
]

# ── Language families (Groups 1 and 2). One catalogue entry is generated per language. ──
LANG_A_UNITS = [
    U("P1", "Paper 1 · Guided analysis of unseen texts",
      "P1.1|Analysing unseen texts and guiding questions|guided textual analysis;unseen text;guiding question",
      "P1.2|Stylistic and literary features bank|literary device;imagery;tone;structure;stylistic features",
      "P1.3|Timed Paper 1 practice|paper 1;commentary"),
    U("P2", "Paper 2 · Comparative essay",
      "P2.1|Works studied: themes, context and quotation bank|comparative essay;themes;quotation",
      "P2.2|Comparative essay planning and thesis|comparative essay;thesis;line of argument",
      "P2.3|Timed Paper 2 practice|paper 2;comparative"),
    U("AOE", "Areas of exploration and concepts",
      "A.1|Readers, writers and texts|readers writers and texts", "A.2|Time and space|time and space;context", "A.3|Intertextuality: connecting texts|intertextuality",
      "A.4|Seven concepts (identity, culture, creativity, communication, perspective, transformation, representation)|identity;representation;perspective"),
    U("CW", "Coursework", "IO|Individual oral (global issue)|individual oral;global issue", "HLE|HL essay|hl essay;line of inquiry|HL"),
]
LANG_A_ASSESS = {
    "SL": [P("Paper 1", 75, 35, "Guided analysis of one unseen text · 20 marks"), P("Paper 2", 105, 35, "Comparative essay on two works · 30 marks"), IA("Individual oral", 30, "15 minutes: two extracts linked by a global issue.")],
    "HL": [P("Paper 1", 135, 35, "Guided analysis of two unseen texts · 40 marks"), P("Paper 2", 105, 25, "Comparative essay on two works · 30 marks"), IA("HL essay", 20, "1,200–1,500 words on one work or body of work."), IA("Individual oral", 20, "15 minutes: two extracts linked by a global issue.")],
}
LANG_B_UNITS = [
    U("TH", "Themes and vocabulary",
      "TH.1|Identities|identity;lifestyle;health;beliefs", "TH.2|Experiences|experiences;leisure;holidays;migration;customs",
      "TH.3|Human ingenuity|technology;media;arts;innovation", "TH.4|Social organization|community;education;work;law", "TH.5|Sharing the planet|environment;human rights;globalization;peace"),
    U("SK", "Paper skills",
      "SK.1|Paper 1 · Writing and text types|text types;formal letter;blog;article;register", "SK.2|Paper 2 · Listening comprehension|listening comprehension;audio",
      "SK.3|Paper 2 · Reading comprehension|reading comprehension;text booklet", "SK.4|Grammar and accuracy|grammar;tenses;conjugation;connectors"),
    U("CW", "Oral", "IO|Individual oral|individual oral;visual stimulus;literary extract"),
]
LANG_B_ASSESS = {
    "SL": [P("Paper 1", 75, 25, "Writing · one task of 250–400 words · 30 marks"), P("Paper 2", 105, 50, "Listening (45 min) + reading (60 min) · 65 marks"), IA("Individual oral", 25, "Conversation based on a visual stimulus.")],
    "HL": [P("Paper 1", 90, 25, "Writing · one task of 450–600 words · 30 marks"), P("Paper 2", 120, 50, "Listening (60 min) + reading (60 min) · 65 marks"), IA("Individual oral", 25, "Conversation based on a literary extract.")],
}
AB_INITIO_ASSESS = {
    "SL": [P("Paper 1", 60, 25, "Writing · two tasks · 30 marks"), P("Paper 2", 105, 50, "Listening (45 min) + reading (60 min) · 65 marks"), IA("Individual oral", 25, "Conversation based on a visual stimulus.")],
}

LANGUAGES_A = ["English", "Spanish", "French", "German", "Chinese", "Japanese", "Korean", "Italian", "Portuguese", "Russian", "Arabic", "Dutch",
               "Swedish", "Norwegian", "Danish", "Finnish", "Turkish", "Indonesian", "Polish", "Hindi", "Modern Greek", "Thai", "Vietnamese", "Malay"]
LANGUAGES_B = ["English", "French", "Spanish", "German", "Chinese", "Japanese", "Italian", "Korean", "Indonesian", "Portuguese", "Arabic", "Swedish",
               "Norwegian", "Hindi", "Finnish", "Dutch", "Danish", "Russian", "Swahili", "Hebrew"]
LANGUAGES_AB = ["French", "Spanish", "Mandarin", "English", "Japanese", "German", "Italian", "Russian", "Arabic"]
# Alternate spellings that appear in file names on the drive.
LANG_ALIASES = {"Chinese": ["chinese", "mandarin", "chi"], "Mandarin": ["mandarin", "chinese", "mandarin chinese"], "English": ["english", "eng"],
                "Swahili": ["swahili", "kiswahili"], "Modern Greek": ["modern greek"]}


def _lang_names(lang: str) -> list[str]:
    return LANG_ALIASES.get(lang, [lang.lower()])


def language_subject(prefix: str, lang: str) -> dict | None:
    """Catalogue entry for one language course. prefix: lang_a_ll | lang_a_lit | lang_b | ab_initio."""
    al = _lang_names(lang)
    low = lang.lower()
    if prefix == "lang_a_ll":
        return dict(
            key=f"lang_a_ll:{lang}", name=f"{lang} A: Language and Literature", short=f"{lang} A L&L", group=1, levels=["HL", "SL"], syllabus_from=2021, family="lang_a",
            language=lang,
            papers=[f"{a} a language and literature" for a in al] + [f"{a} a l&l" for a in al] + [f"{a} l and l" for a in al] + [f"{a} l&l" for a in al],
            papers_legacy=[(f"{a} a1", "Old course (A1)") for a in al] + [(f"{a} a2", "Old course (A2)") for a in al],
            books=[f"group 1 - studies in language and literature/{low} a language and literature"],
            qb=[], qb_paper=[], sme=[f"{low} a"],
            sites=(["ThinkIB/englisha", "StudyIB/englishalanglit"] if lang == "English" else []),
            names=[f"{a} a - language and literature" for a in al] + [f"{a} a language and literature" for a in al] + [f"{a} a - literature and language and literature" for a in al],
            assessment=LANG_A_ASSESS, units=LANG_A_UNITS)
    if prefix == "lang_a_lit":
        return dict(
            key=f"lang_a_lit:{lang}", name=f"{lang} A: Literature", short=f"{lang} A Lit", group=1, levels=["HL", "SL"], syllabus_from=2021, family="lang_a",
            language=lang,
            papers=[f"{a} a literature" for a in al] + [f"{a} a lit" for a in al],
            papers_legacy=[],
            books=[f"group 1 - studies in language and literature/{low} a literature"],
            qb=[], qb_paper=[], sme=[], sites=[],
            names=[f"{a} a - literature" for a in al] + [f"{a} a literature" for a in al],
            assessment=LANG_A_ASSESS, units=LANG_A_UNITS)
    if prefix == "lang_b":
        bookdirs = [f"group 2 - language acquisition/{low} b"] + (["group 2 - language acquisition/mandarin chinese b"] if lang == "Chinese" else [])
        return dict(
            key=f"lang_b:{lang}", name=f"{lang} B", short=f"{lang} B", group=2, levels=["HL", "SL"], syllabus_from=2020, family="lang_b", language=lang,
            papers=[f"{a} b" for a in al], papers_legacy=[], books=bookdirs, qb=[], qb_paper=[], sme=[f"{low} b"],
            sites=(["ThinkIB/englishb"] if lang == "English" else ["StudyIB/spanishb"] if lang == "Spanish" else []),
            names=[f"{a} b" for a in al], assessment=LANG_B_ASSESS, units=LANG_B_UNITS)
    if prefix == "ab_initio":
        bookdirs = [f"group 2 - language acquisition/{low} ab initio"] + (["group 2 - language acquisition/mandarin chinese ab initio"] if lang == "Mandarin" else [])
        return dict(
            key=f"ab_initio:{lang}", name=f"{lang} ab initio", short=f"{lang} ab initio", group=2, levels=["SL"], syllabus_from=2020, family="lang_b", language=lang,
            papers=[f"{a} ab initio" for a in al] + [f"{a} abinitio" for a in al] + [f"{a} ab" for a in al], papers_legacy=[], books=bookdirs, qb=[], qb_paper=[],
            sme=[f"{low} ab initio"], sites=[], names=[f"{a} ab initio" for a in al],
            assessment=AB_INITIO_ASSESS, units=LANG_B_UNITS)
    return None


def _build_language_subjects() -> list[dict]:
    out = []
    for lang in LANGUAGES_A:
        out.append(language_subject("lang_a_ll", lang))
        out.append(language_subject("lang_a_lit", lang))
    for lang in LANGUAGES_B:
        out.append(language_subject("lang_b", lang))
    for lang in LANGUAGES_AB:
        out.append(language_subject("ab_initio", lang))
    return out


SUBJECTS.extend(_build_language_subjects())

# Core components. They are not timetabled like exam subjects but have their own resources and feedback rubrics.
CORE = [
    dict(key="tok", name="Theory of Knowledge", short="TOK", names=["theory of knowledge", "tok"],
         paths=["theoryofknowledge.net", "ib books/core - theory of knowledge", "core - theory of knowledge"],
         assessment=[IA("TOK essay", 67, "Max 1,600 words on one of six prescribed titles."), IA("TOK exhibition", 33, "Three objects + 950-word commentary on one IA prompt.")]),
    dict(key="ee", name="Extended Essay", short="EE", names=["extended essay"],
         paths=["ib official ee exemplars", "ib books/core - extended essay", "core - extended essay"],
         assessment=[IA("Extended essay", 100, "Max 4,000 words + reflections.")]),
    dict(key="cas", name="Creativity, Activity, Service", short="CAS", names=["creativity, activity and service", "cas"],
         paths=["core - creativity, activity and service"], assessment=[]),
]

GROUP_NAMES = {1: "Studies in Language and Literature", 2: "Language Acquisition", 3: "Individuals and Societies", 4: "Sciences", 5: "Mathematics", 6: "The Arts"}

# Typical first written exam date used until a student sets their own (month, day).
SESSION_START = {"May": (4, 27), "November": (10, 27)}
SESSION_END = {"May": (5, 21), "November": (11, 18)}
